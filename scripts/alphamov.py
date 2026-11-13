#!/usr/bin/env python3
"""Turn a transparent VP9 WebM (an animated insert rendered by a sub-agent, see references/overlays.md) into a .mov
with alpha that Edits can import, frame for frame.

Usage:  PY alphamov.py <in.webm> <out.mov> [--fps 30] [--codec prores|hevc]
Put <out.mov> inside the project's media/ folder (Edits only imports from under ~/Movies).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layerkit  # noqa: E402
import skillenv  # noqa: E402


def main():
    skillenv.utf8_stdio()
    a = sys.argv[1:]
    if len(a) < 2 or a[0] in ('-h', '--help'):
        sys.exit(__doc__)
    fps, codec = '30', 'prores'
    if '--fps' in a:
        fps = a[a.index('--fps') + 1]
    if '--codec' in a:
        codec = a[a.index('--codec') + 1]
    layerkit.check_codec(codec)
    src, dst = skillenv.path_arg(a[0]), skillenv.path_arg(a[1])
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    layerkit.webm_to_alpha_mov(src, dst, fps, codec)
    n_in, n_out = layerkit.frames(src, vp9_alpha=True), layerkit.frames(dst)
    alpha = layerkit.has_alpha(dst)
    print(f'{dst}  frames {n_in} -> {n_out}  alpha {alpha}')
    sys.exit(0 if n_in == n_out and alpha is not False else 1)


if __name__ == '__main__':
    main()
