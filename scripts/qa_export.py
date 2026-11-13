#!/usr/bin/env python3
"""Read-only QA of a reel exported by Edits: frame pairs around every cut, stills at chosen moments, audio levels.
It writes JPGs and text only, never video.

Usage:  PY qa_export.py <project_dir> <export.mp4> [--cuts 3.06,7.48,...] [--at 1.2,5.0,...]
  --cuts  cut times in seconds as read back from the Edits timeline (preferred). Without it, cuts are the running
          sum of the EDL segment durations, which is right only if Edits did not snap or move anything.
  --at    extra moments to inspect (text entries/exits, behind-head words).
Writes  work/qa/cut_check.jpg   before|after pairs for every cut (LOOK at it: every 'after' frame shows the new shot
                                and its layer, no leftover speaker layer or text from the previous shot)
        work/qa/at_<t>.jpg      full-size stills for --at (check safe zone, face, behind-head readability)
Prints  max/mean volume of the export (voice peaks should land around -2 to -5 dB).
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layerkit  # noqa: E402
import skillenv  # noqa: E402


def floats(a, flag):
    return [float(x) for x in a[a.index(flag) + 1].split(',') if x] if flag in a else []


def main():
    skillenv.utf8_stdio()
    a = sys.argv[1:]
    if len(a) < 2 or a[0] in ('-h', '--help'):
        sys.exit(__doc__)
    FF = skillenv.tool('ffmpeg')
    proj, export = skillenv.path_arg(a[0]), skillenv.path_arg(a[1])
    qa = os.path.join(proj, 'work', 'qa')
    os.makedirs(qa, exist_ok=True)
    fps = layerkit.probe(export)['fps']
    cuts = floats(a, '--cuts')
    if not cuts:
        with open(os.path.join(proj, 'edl.json'), encoding='utf-8') as fh:
            segs = json.load(fh)['segments']
        t = 0.0
        for s in segs[:-1]:
            t += s['out'] - s['in']
            cuts.append(t)
        print('cuts from EDL durations (pass --cuts from the timeline when you have it)')
    pngs = []
    for c in cuts:
        n = round(c * fps)
        for k in (n - 1, n):
            p = os.path.join(qa, f'f{k}.png')
            subprocess.run([FF, '-loglevel', 'error', '-y', '-i', export, '-vf', f'select=eq(n\\,{k}),scale=150:-2',
                            '-frames:v', '1', p], check=True)
            pngs.append(p)
    if pngs:
        ins = sum((['-i', p] for p in pngs), [])
        sheet = os.path.join(qa, 'cut_check.jpg')
        subprocess.run([FF, '-loglevel', 'error', '-y', *ins, '-filter_complex', f'hstack={len(pngs)}', sheet],
                       check=True)
        print('cuts at', [round(c, 3) for c in cuts], '->', sheet)
    for t in floats(a, '--at'):
        p = os.path.join(qa, f'at_{t:.2f}.jpg')
        subprocess.run([FF, '-loglevel', 'error', '-y', '-ss', f'{t:.3f}', '-i', export, '-frames:v', '1', p],
                       check=True)
        print('still', p)
    err = subprocess.run([FF, '-hide_banner', '-i', export, '-af', 'volumedetect', '-vn', '-f', 'null', '-'],
                         **skillenv.TEXT).stderr
    vol = dict(re.findall(r'(max_volume|mean_volume): (-?[\d.]+) dB', err))
    print(f"audio max {vol.get('max_volume', '?')} dB, mean {vol.get('mean_volume', '?')} dB"
          + ('  << NO AUDIO STREAM' if not vol else ''))


if __name__ == '__main__':
    main()
