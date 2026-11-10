#!/usr/bin/env python3
"""Behind-head layers for Edits: cut the speaker out of ONE EDL segment, straight from the original clip, and write
a frame-aligned subject layer with alpha. In Edits the stack is: base clip, text, this layer. The text stays an
editable Edits text; only the speaker's pixels come from here.

Usage:  PY matte.py <project_dir> [segment ids...] [--codec prores|hevc] [--force] [-- extra remove-background args]
        no ids = every segment that has a text with "layer": "behind" in edl.json

Reads   <project>/edl.json, <project>/sources.json (originals, from ingest.py)
Writes  <project>/media/layers/<id>-<key>.mov     the speaker + alpha, starts exactly at the segment's in point
        <project>/layers.json                     manifest (file, key, fps, frames, size, head position) per segment
        <project>/work/layers/<id>-<key>/         intermediates (src.mp4, subject.webm, alpha stills)

Geometry: the layer is the SOURCE frame, same aspect, no crop and no zoom. Edits must give it the same transform as
the base clip (the segment's zoom/cx/cy), so the two stay pixel-aligned whatever Edits does with them. Width is the
source width capped at 1080 * zoom, so a 1.9x punch-in from 4K still gets a sharp speaker.

Timing: the layer runs at the source's frame rate with exactly the frames of [in, out). Place it on the timeline at
the base segment's start, same duration. Any trim of the base segment in Edits must be mirrored on the layer (the
reconcile loop does it from the EDL, never by hand).

Cache: <key> hashes the source (path, size, mtime), in, out, width, codec and the HyperFrames version. Unchanged
segments are never cut out twice; a trimmed segment gets a new key and a new file (old files are kept).
Speed: ~7 s per second of 1080p footage on Apple Silicon, more at 4K widths. One run at a time (~1.5 GB of RAM).
"""
import fractions
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layerkit  # noqa: E402
import skillenv  # noqa: E402

CANVAS_AR = 9 / 16


def even(v):
    return max(2, int(round(v / 2)) * 2)


def layer_size(src_w, src_h, zoom):
    w = min(src_w, even(1080 * max(1.0, zoom)))
    return even(w), even(w * src_h / src_w)


def cache_key(src, seg, width, codec):
    st = os.stat(src)
    raw = json.dumps([os.path.abspath(src), st.st_size, int(st.st_mtime), round(seg['in'], 3), round(seg['out'], 3),
                      width, codec, skillenv.HYPERFRAMES])
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]


def clamp_center(c, zoom):
    """Centre of a zoom-z crop, kept inside the frame (same rule the EDL's zoom/cx/cy has always meant)."""
    if zoom <= 1:
        return 0.5
    half = 0.5 / zoom
    return min(max(c, half), 1 - half)


def to_canvas(v, zoom, c):
    """Source-normalised coordinate -> canvas-normalised, for a 9:16 source framed with zoom around centre c."""
    return 0.5 + (v - clamp_center(c, zoom)) * max(1.0, zoom)


def behind_segments(edl):
    ids = []
    for t in edl.get('texts', []):
        if t.get('layer') == 'behind' and t.get('segment') not in ids:
            ids.append(t['segment'])
    return ids


def head_position(webm, still_dir, seg_id, d):
    """Head top / x-span / body box at 20, 50 and 80% of the layer, normalised to the layer frame (0..1)."""
    from PIL import Image   # the skill's venv has Pillow; imported here so --help works without it
    rows = []
    for k, f in enumerate((.2, .5, .8)):
        png = os.path.join(still_dir, f'{skillenv.safe_name(seg_id)}_{k}.png')
        subprocess.run([skillenv.tool('ffmpeg'), '-loglevel', 'error', '-y', '-c:v', 'libvpx-vp9',
                        '-ss', f'{d * f:.3f}', '-i', webm, '-frames:v', '1', '-vf', 'alphaextract,scale=270:-2', png],
                       check=True)
        im = Image.open(png).convert('L')
        px, (w, h) = im.load(), im.size
        ys = [y for y in range(h) if any(px[x, y] > 128 for x in range(0, w, 2))]
        if not ys:
            rows.append(None)
            continue
        top = ys[0]
        probe_y = min(h - 1, top + max(1, h // 20))
        xs = [x for x in range(w) if px[x, probe_y] > 128] or [0, w - 1]
        bb = im.point(lambda v: 255 if v > 128 else 0).getbbox()
        rows.append({'at': f, 'head_top': round(top / h, 4), 'head_x': [round(xs[0] / w, 4), round(xs[-1] / w, 4)],
                     'body': [round(bb[0] / w, 4), round(bb[1] / h, 4), round(bb[2] / w, 4), round(bb[3] / h, 4)]})
    return rows


def summarize(rows, seg, src_ar):
    found = [r for r in rows if r]
    if not found:
        return {'samples': rows, 'warning': 'no subject found in the layer'}
    tops = [r['head_top'] for r in found]
    out = {'samples': rows, 'head_top_min': min(tops), 'head_top_spread': round(max(tops) - min(tops), 4)}
    if abs(src_ar - CANVAS_AR) < 0.01:
        z, cy = seg.get('zoom', 1.0), seg.get('cy', 0.5)
        out['canvas_head_top'] = round(to_canvas(min(tops), z, cy), 4)
        out['canvas_head_top_px'] = round(out['canvas_head_top'] * 1920)
    else:
        out['warning'] = 'source is not 9:16: canvas positions not computed, place by preview frame'
    if out['head_top_spread'] > 0.03:
        out['moving'] = True   # the head moves during the segment: put the word in front over the chest instead
    return out


def build(proj, seg, sources, codec, force, extra):
    src = sources[seg['clip']]
    info = layerkit.probe(src)
    fps = info['fps']
    w, h = layer_size(info['width'], info['height'], seg.get('zoom', 1.0))
    key = cache_key(src, seg, w, codec)
    name = f"{skillenv.safe_name(seg['id'])}-{key}"
    mov = os.path.join(proj, 'media', 'layers', name + '.mov')
    work = os.path.join(proj, 'work', 'layers', name)
    os.makedirs(os.path.dirname(mov), exist_ok=True)
    os.makedirs(work, exist_ok=True)
    d = seg['out'] - seg['in']
    expected = round(d * fps)
    webm = os.path.join(work, 'subject.webm')

    if os.path.isfile(mov) and os.path.isfile(webm) and not force:
        print(f"{seg['id']:10s} cached  {os.path.basename(mov)}")
    else:
        print(f"{seg['id']:10s} cutting {d:.2f}s at {w}x{h} {float(fps):.3f}fps ({codec})", flush=True)
        f = f'{fps.numerator}/{fps.denominator}'
        subprocess.run([skillenv.tool('ffmpeg'), '-loglevel', 'error', '-y', '-ss', f"{seg['in']:.3f}", '-i', src,
                        '-t', f'{d:.3f}', '-map', '0:v:0', '-an',
                        '-vf', f'scale={w}:{h}:flags=lanczos,fps={f},setpts=N/({f})/TB',
                        '-c:v', 'libx264', '-crf', '12', '-preset', 'medium', '-pix_fmt', 'yuv420p',
                        os.path.join(work, 'src.mp4')], check=True)
        layerkit.remove_background('src.mp4', 'subject.webm', work, extra)
        layerkit.webm_to_alpha_mov(webm, mov, fps, codec)

    n_src = layerkit.frames(os.path.join(work, 'src.mp4'))
    n_sub = layerkit.frames(webm, vp9_alpha=True)
    n_mov = layerkit.frames(mov)
    ok = n_src == n_sub == n_mov and n_mov is not None
    alpha = layerkit.has_alpha(mov)
    print(f"{'':10s} frames src {n_src} / cutout {n_sub} / layer {n_mov} (expected ~{expected})"
          + ('' if ok else '  << MISMATCH: the layer will drift, re-run with --force')
          + ('' if alpha is not False else '  << NO ALPHA in the .mov'))
    rows = head_position(webm, work, seg['id'], d)
    return {'file': os.path.abspath(mov), 'key': key, 'clip': seg['clip'], 'in': seg['in'], 'out': seg['out'],
            'fps': f'{fps.numerator}/{fps.denominator}', 'frames': n_mov, 'size': [w, h], 'codec': codec,
            'frames_ok': ok, 'alpha': alpha,
            'transform': {'zoom': seg.get('zoom', 1.0), 'cx': seg.get('cx', 0.5), 'cy': seg.get('cy', 0.5)},
            'head': summarize(rows, seg, info['width'] / info['height'])}


def main():
    skillenv.utf8_stdio()
    argv = sys.argv[1:]
    extra = []
    if '--' in argv:
        i = argv.index('--')
        argv, extra = argv[:i], argv[i + 1:]
    if not argv or argv[0] in ('-h', '--help'):
        sys.exit(__doc__)
    codec, force = 'prores', False
    if '--codec' in argv:
        i = argv.index('--codec')
        codec = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if '--force' in argv:
        force = True
        argv.remove('--force')
    if codec not in layerkit.CODECS:
        sys.exit(f'--codec must be one of {layerkit.CODECS}')
    layerkit.check_codec(codec)
    proj, wanted = skillenv.path_arg(argv[0]), argv[1:]
    with open(os.path.join(proj, 'edl.json'), encoding='utf-8') as fh:
        edl = json.load(fh)
    with open(os.path.join(proj, 'sources.json'), encoding='utf-8') as fh:
        sources = json.load(fh)
    segs = {s['id']: s for s in edl['segments']}
    ids = wanted or behind_segments(edl)
    if not ids:
        sys.exit('No segment asks for a behind-head layer (no text with "layer": "behind"). Nothing to do.')
    unknown = [i for i in ids if i not in segs]
    if unknown:
        sys.exit(f'Not in edl.json segments: {unknown}')
    manifest_path = os.path.join(proj, 'layers.json')
    manifest = {}
    if os.path.isfile(manifest_path):
        with open(manifest_path, encoding='utf-8') as fh:
            manifest = json.load(fh)
    for i in ids:
        manifest[i] = build(proj, segs[i], sources, codec, force, extra)
        with open(manifest_path, 'w', encoding='utf-8') as fh:   # after each segment: a crash keeps finished ones
            json.dump(manifest, fh, indent=1)
    bad = [i for i in ids if not manifest[i]['frames_ok'] or manifest[i]['alpha'] is False]
    print(f'layers.json updated ({len(ids)} segment(s))' + (f'  PROBLEMS: {bad}' if bad else ''))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
