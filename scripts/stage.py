#!/usr/bin/env python3
"""Copy what Edits must import into the project's media/ folder. Edits is sandboxed: it imports from ~/Movies and
refuses ~/Downloads, ~/Desktop and temp folders, and it does not expand `~`. So the project lives under ~/Movies and
every import uses an absolute path from media.json.

Usage:  PY stage.py <project_dir> [--sfx name1,name2]
Reads   <project>/sources.json (originals, from ingest.py)
Writes  <project>/media/<cN>.<ext>        copies of the originals (APFS clone on macOS: instant, no extra space)
        <project>/media/sfx/<name>.mp3     the requested sound effects from the skill's assets
        <project>/media.json              {"c1": "/Users/.../media/c1.mov", "sfx": {"pop": "..."}}
Originals are only read. A copy that already exists with the same size is kept.
"""
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

SFX_DIR = os.path.join(skillenv.SKILL_DIR, 'assets', 'hyperframes', 'assets', 'sfx')


def under_movies(p):
    movies = os.path.realpath(os.path.join(os.path.expanduser('~'), 'Movies'))
    return os.path.realpath(p).startswith(movies + os.sep)


def copy(src, dst):
    if os.path.isfile(dst) and os.path.getsize(dst) == os.path.getsize(src):
        return 'kept'
    tmp = dst + '.part'
    cp = shutil.which('cp') if sys.platform == 'darwin' else None
    if cp and subprocess.run([cp, '-c', src, tmp], capture_output=True).returncode == 0:   # clonefile(2)
        os.replace(tmp, dst)
        return 'cloned'
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)
    return 'copied'


def main():
    skillenv.utf8_stdio()
    a = sys.argv[1:]
    if not a or a[0] in ('-h', '--help'):
        sys.exit(__doc__)
    proj = os.path.abspath(skillenv.path_arg(a[0]))
    sfx = a[a.index('--sfx') + 1].split(',') if '--sfx' in a else []
    if not under_movies(proj):
        print(f'WARNING {proj} is not under ~/Movies: Edits will probably refuse to import from it.')
    with open(os.path.join(proj, 'sources.json'), encoding='utf-8') as fh:
        sources = json.load(fh)
    media = os.path.join(proj, 'media')
    os.makedirs(media, exist_ok=True)
    out = {}
    for cid, src in sources.items():
        dst = os.path.join(media, cid + os.path.splitext(src)[1].lower())
        how = copy(src, dst)
        out[cid] = dst
        print(f'{cid:4s} {how:7s} {dst}')
    if sfx:
        os.makedirs(os.path.join(media, 'sfx'), exist_ok=True)
        out['sfx'] = {}
        for n in sfx:
            src = os.path.join(SFX_DIR, n + '.mp3')
            if not os.path.isfile(src):
                print(f'sfx  missing {src} (run setup.py)')
                continue
            dst = os.path.join(media, 'sfx', n + '.mp3')
            copy(src, dst)
            out['sfx'][n] = dst
            print(f'sfx  {n:14s} {dst}')
    with open(os.path.join(proj, 'media.json'), 'w', encoding='utf-8') as fh:
        json.dump(out, fh, indent=1)


if __name__ == '__main__':
    main()
