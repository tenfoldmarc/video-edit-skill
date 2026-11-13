#!/usr/bin/env python3
"""Shared helpers for the layers this skill hands to Edits: probing, HyperFrames runs with readable progress, and
conversion of a transparent VP9 WebM into a .mov with alpha that macOS (and so Edits) can decode.

Not a command on its own; matte.py and alphamov.py import it. Standard library only.

Why a .mov: HyperFrames writes VP9 + alpha in WebM, which AVFoundation does not decode with its alpha. Edits is a
macOS app, so layers go in as ProRes 4444 (any ffmpeg can write it, large files) or HEVC with alpha (small, needs
the hevc_videotoolbox encoder, so only on a Mac). Which one Edits accepts is probed once in discovery.
"""
import collections
import fractions
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')
CODECS = ('prores', 'hevc')


def probe(f):
    """-> dict(width, height, fps (Fraction), duration, pix_fmt) of the first video stream."""
    out = subprocess.run([skillenv.tool('ffprobe'), '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                          'stream=width,height,r_frame_rate,pix_fmt:stream_side_data=rotation:format=duration',
                          '-of', 'json', f], **skillenv.TEXT).stdout
    j = json.loads(out)
    s = j['streams'][0]
    rot = 0
    for sd in s.get('side_data_list', []) or []:
        rot = int(sd.get('rotation', 0) or 0)
    w, h = s['width'], s['height']
    if abs(rot) in (90, 270):   # phone footage stored landscape with a rotation flag
        w, h = h, w
    return {'width': w, 'height': h, 'fps': fractions.Fraction(s['r_frame_rate']), 'pix_fmt': s.get('pix_fmt', ''),
            'duration': float(j.get('format', {}).get('duration', 0) or 0)}


def frames(f, vp9_alpha=False):
    """Decoded frame count (vp9_alpha is accepted for readability at call sites; the count needs no alpha decode)."""
    out = subprocess.run([skillenv.tool('ffprobe'), '-v', 'error', '-count_frames', '-select_streams', 'v:0',
                          '-show_entries', 'stream=nb_read_frames', '-of', 'csv=p=0', f], **skillenv.TEXT).stdout
    v = out.strip().split(',')[0]
    return int(v) if v.isdigit() else None


def has_encoder(name):
    out = subprocess.run([skillenv.tool('ffmpeg'), '-hide_banner', '-encoders'], **skillenv.TEXT).stdout
    return any(line.split()[1:2] == [name] for line in out.splitlines() if line.startswith(' '))


def split_progress(buf):
    """-> (finished lines, unfinished rest). HyperFrames redraws its spinner with cursor escape codes instead of
    newlines, so every escape code counts as a line break, and the spinner glyph in front is dropped."""
    *lines, rest = re.split(r'[\r\n]+', ANSI.sub('\n', buf))
    return [l for l in (re.sub(r'^[^\w\[(]+', '', l).strip() for l in lines) if l], rest


def run_quiet(argv, env, cwd, every=30):
    """Run like `| tail -1`, but print the newest progress line every `every` seconds so a long background run is
    visibly alive. Returns (exit code, last lines)."""
    last, shown, t_print = collections.deque(maxlen=25), '', time.time()
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    buf = ''
    while True:
        chunk = proc.stdout.read1(4096)
        if not chunk:
            break
        lines, buf = split_progress(buf + chunk.decode('utf-8', 'replace'))
        for l in lines:
            if not last or l != last[-1]:
                last.append(l)
        if last and last[-1] != shown and time.time() - t_print >= every:
            shown, t_print = last[-1], time.time()
            print(shown, flush=True)
    for l in split_progress(buf + '\n')[0]:
        last.append(l)
    return proc.wait(), list(last)


def remove_background(src_name, out_name, cwd, extra=()):
    """`hyperframes remove-background` on a file in cwd (relative names: nothing with the user's folder name goes
    through npx's argument handling). Exits with the tail of its output on failure."""
    argv, env = skillenv.hyperframes_command(['remove-background', src_name, '-o', out_name, '--quality', 'best',
                                              *extra])
    code, last = run_quiet(argv, env, cwd)
    if code != 0:
        print('\n'.join(last))
        sys.exit(f'remove-background failed (exit {code}). Lines above are the end of its output.')
    return last


def alpha_args(codec):
    """ffmpeg output arguments for a .mov with alpha."""
    if codec == 'prores':
        return ['-c:v', 'prores_ks', '-profile:v', '4444', '-pix_fmt', 'yuva444p10le', '-vendor', 'apl0']
    if codec == 'hevc':
        return ['-c:v', 'hevc_videotoolbox', '-alpha_quality', '0.75', '-q:v', '65', '-tag:v', 'hvc1',
                '-pix_fmt', 'bgra']
    raise ValueError(f'unknown codec {codec!r}, expected one of {CODECS}')


def check_codec(codec):
    enc = {'prores': 'prores_ks', 'hevc': 'hevc_videotoolbox'}[codec]
    if not has_encoder(enc):
        sys.exit(f'This ffmpeg has no {enc} encoder. Use --codec prores, or an ffmpeg built with VideoToolbox (Mac).')


def webm_to_alpha_mov(webm, mov, fps, codec='prores'):
    """Transparent VP9 WebM -> .mov with alpha at a constant `fps` (Fraction or 'N/D'), frame for frame."""
    fps = fractions.Fraction(fps)
    tmp = mov + '.part.mov'
    subprocess.run([skillenv.tool('ffmpeg'), '-loglevel', 'error', '-y', '-c:v', 'libvpx-vp9', '-i', webm,
                    '-map', '0:v:0', '-an', '-vf', f'setpts=N/({fps.numerator}/{fps.denominator})/TB',
                    '-r', f'{fps.numerator}/{fps.denominator}', '-fps_mode', 'cfr', *alpha_args(codec), tmp],
                   check=True)
    os.replace(tmp, mov)


def has_alpha(mov):
    """True when the file's pixel format carries alpha (ProRes 4444 reports yuva444p*). HEVC-with-alpha keeps the
    alpha in a second layer that ffprobe does not report, so for HEVC this returns None (unknown)."""
    p = probe(mov)
    if 'hevc' in subprocess.run([skillenv.tool('ffprobe'), '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                                 'stream=codec_name', '-of', 'csv=p=0', mov], **skillenv.TEXT).stdout:
        return None
    return 'a' in p['pix_fmt'].replace('gray', '')
