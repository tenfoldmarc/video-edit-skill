#!/usr/bin/env python3
"""/video-edit first-run checks, for macOS, Linux (and WSL) and Windows. Safe to re-run: it only reports and fills
in what is missing. Standard library only, because it runs before the skill's own Python environment exists.

Run it with whichever Python the machine has:   python3 setup.py   |   python setup.py   |   py -3 setup.py

  1. ffmpeg + ffprobe on PATH
  2. Node 22+ (HyperFrames renders with it; an nvm / Homebrew / installer copy is picked up even when an older
     Node is the default)
  3. Python 3.10+ and a venv inside the skill with faster-whisper + Pillow (transcription, head tracking)
  4. Sound effects in assets/hyperframes/assets/sfx (not bundled: the Pixabay license forbids redistributing the files)
  5. Instagram Edits for Mac and its automation server (the editor this skill drives), and which alpha codecs this
     ffmpeg can write for the layers handed to Edits

Prints a STATUS line per item, each with the fix for THIS machine, then READY or NOT READY. Exit code 0 only when
everything is ready. Writes <skill>/.platform.json (os, arch, the venv Python, how to start npx) so the other
scripts and SKILL.md read the right commands instead of detecting again. Nothing is sent anywhere.
"""
import datetime
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

SFX_NAMES = ['whoosh-short', 'pop', 'sparkle', 'click', 'click-soft', 'impact-bass-1']
SFX_URL = 'https://raw.githubusercontent.com/heygen-com/hyperframes/main/skills/media-use/audio/assets/sfx'
RESTART = 'then quit Claude Code completely, reopen it and run /video-edit again'


def fix(what, osn):
    """The one command (or link) that installs `what` on this OS."""
    table = {
        'ffmpeg': {'macos': 'brew install ffmpeg',
                   'linux': 'sudo apt install ffmpeg',
                   'windows': f'winget install --id Gyan.FFmpeg -e   ({RESTART})'},
        'node': {'macos': 'brew install node   (or the installer from https://nodejs.org)',
                 'linux': 'install Node 22 LTS from https://nodejs.org (or: nvm install 22). apt\'s own nodejs is often too old',
                 'windows': f'winget install --id OpenJS.NodeJS.LTS -e   ({RESTART})'},
        'python': {'macos': 'brew install python   (or the installer from https://python.org)',
                   'linux': 'sudo apt install python3 python3-venv',
                   'windows': f'winget install --id Python.Python.3.12 -e   ({RESTART})'},
        'venv': {'macos': 'brew install python',
                 'linux': 'sudo apt install python3-venv',
                 'windows': f'winget install --id Python.Python.3.12 -e   ({RESTART})'},
    }
    return table[what][osn]


def say(line):
    print(line, flush=True)


# ------------------------------------------------------------------ 1. ffmpeg
def check_ffmpeg(osn):
    found = {n: skillenv.find_tool(n, osn) for n in ('ffmpeg', 'ffprobe')}
    if all(p and on_path for p, on_path in found.values()):
        ff = found['ffmpeg'][0]
        try:
            ver = subprocess.run([ff, '-version'], **skillenv.TEXT, timeout=30).stdout.split()[2]
            enc = subprocess.run([ff, '-hide_banner', '-encoders'], **skillenv.TEXT, timeout=30).stdout
        except (OSError, IndexError, subprocess.SubprocessError):
            ver, enc = 'version unknown', 'libx264 libvpx-vp9'
        lacking = [e for e in ('libx264', 'libvpx-vp9') if e not in enc]
        if lacking:   # cut-down builds: the reel is H.264, the cutout is VP9 with alpha
            say(f"STATUS ffmpeg INCOMPLETE ({ver} at {ff} has no {' / '.join(lacking)}) -> install a full build: {fix('ffmpeg', osn)}")
            return False, None, None
        say(f'STATUS ffmpeg OK ({ver})')
        return True, ff, found['ffprobe'][0]
    if all(p for p, _ in found.values()):
        where = os.path.dirname(found['ffmpeg'][0])
        if osn == 'windows':
            say(f'STATUS ffmpeg INSTALLED BUT NOT VISIBLE YET (found in {where}) -> this session started before it was '
                f'installed: quit Claude Code completely, reopen it and run /video-edit again')
        else:
            say(f'STATUS ffmpeg NOT ON PATH (found in {where}) -> add that folder to your PATH, then reopen Claude Code')
        return False, None, None
    say(f"STATUS ffmpeg MISSING -> {fix('ffmpeg', osn)}")
    return False, None, None


# ------------------------------------------------------------------ 2. node
def check_node(osn):
    node, ver, on_path = skillenv.find_node(osn)
    if node and skillenv.node_major(ver) >= skillenv.MIN_NODE:
        npx = skillenv.npx_command(node, osn)
        if npx:
            say(f'STATUS node OK ({ver})' if on_path else f'STATUS node OK ({ver}, using {node})')
            return True, node, ver, npx
        say(f"STATUS node found ({ver}) but npx is missing next to it -> reinstall Node: {fix('node', osn)}")
        return False, node, ver, None
    have = f'found {ver}, need {skillenv.MIN_NODE}+' if ver else 'not found'
    say(f"STATUS node MISSING or < {skillenv.MIN_NODE} ({have}) -> {fix('node', osn)}")
    return False, None, ver, None


# ------------------------------------------------------------------ 3. python + venv
def base_python():
    """The interpreter to build the venv with: this one when it is 3.10+, otherwise a newer one on PATH, otherwise
    this one anyway when it is 3.9 (the old setup.sh used whatever `python3` was, and 3.9 still works)."""
    if sys.version_info[:2] >= skillenv.MIN_PY:
        return sys.executable, sys.version_info[:2]
    for minor in range(14, 9, -1):
        p = shutil.which(f'python3.{minor}')
        if p:
            return p, (3, minor)
    if sys.version_info[:2] >= skillenv.OLDEST_PY:
        return sys.executable, sys.version_info[:2]
    return None, sys.version_info[:2]


# Versions are pinned so a new upstream release cannot break installs (same pins as the setup.sh hotfix). PyAV 19
# (2026-09-29) removed the `metadata_errors` argument that faster-whisper 1.2.1 still passes, so every transcription
# crashed on fresh installs. A venv that already has PyAV 19 fails the self-test below and is repaired in place.
REQUIREMENTS = ['faster-whisper==1.2.1', 'av>=11,<19', 'pillow']
# imports alone did not catch the PyAV break: decode a tenth of a second of silence the way a transcription does
VENV_SELFTEST = r'''
import os, tempfile, wave
import PIL
from faster_whisper.audio import decode_audio
d = tempfile.mkdtemp(); p = os.path.join(d, 't.wav')
w = wave.open(p, 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b'\0\0' * 1600); w.close()
try:
    decode_audio(p)
finally:
    os.remove(p); os.rmdir(d)
'''


def venv_ok(py):
    if not py or not os.path.isfile(py):
        return False
    try:
        return subprocess.run([py, '-c', VENV_SELFTEST], capture_output=True, timeout=300).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def tail(text, n=12):
    return '\n'.join('        ' + l for l in (text or '').strip().splitlines()[-n:])


def check_python(info):
    osn = info['os']
    py = skillenv.find_venv_python(skillenv.SKILL_DIR, osn)
    if venv_ok(py):
        say('STATUS python venv OK')
        return True, py
    base, ver = base_python()
    if not base:
        say(f"STATUS python MISSING or too old (this is {ver[0]}.{ver[1]}, need 3.10+) -> {fix('python', osn)}")
        return False, None
    if osn == 'windows' and info['python_arch'] == 'arm64':
        say('STATUS python venv CANNOT BE BUILT with this ARM64 Python (the transcription engine has no Windows ARM '
            f'build) -> install the x64 Python: winget install --id Python.Python.3.12 -e --architecture x64   ({RESTART})')
        return False, None
    venv = os.path.join(skillenv.SKILL_DIR, '.venv')
    if py:   # the venv is there but its packages are missing or broken: repair it in place
        say(f'STATUS python venv: repairing {venv} (faster-whisper + Pillow, ~1 min)')
    else:
        say(f'STATUS python venv: creating {venv} (faster-whisper + Pillow, ~1 min)')
        r = subprocess.run([base, '-m', 'venv', venv], **skillenv.TEXT)
        py = skillenv.find_venv_python(skillenv.SKILL_DIR, osn)
        if r.returncode != 0 or not py:
            say(f"STATUS python venv FAILED (could not create it) -> {fix('venv', osn)}")
            say(tail(r.stdout + r.stderr))
            return False, None
    # `python -m pip`, not the pip script: on Windows pip.exe cannot replace itself while it is running
    subprocess.run([py, '-m', 'pip', 'install', '-q', '--upgrade', 'pip'], **skillenv.TEXT)
    r = subprocess.run([py, '-m', 'pip', 'install', '-q'] + REQUIREMENTS, **skillenv.TEXT)
    if r.returncode == 0 and venv_ok(py):
        say('STATUS python venv OK')
        return True, py
    say('STATUS python venv FAILED (pip output below). If it says no matching version / failed building a wheel, this '
        f"Python ({ver[0]}.{ver[1]}) is too new or too old for the packages -> {fix('python', osn)}")
    say(tail(r.stdout + r.stderr))
    return False, py


# ------------------------------------------------------------------ 4. sound effects
def fetch(url, dest):
    tmp = dest + '.part'
    try:
        with urllib.request.urlopen(url, timeout=30) as r, open(tmp, 'wb') as f:
            shutil.copyfileobj(r, f)
    except Exception:   # no certificates in a python.org macOS install, offline, proxy... try the system curl
        curl = shutil.which('curl')
        if curl:
            subprocess.run([curl, '-fsSL', url, '-o', tmp], capture_output=True)
    if os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
        os.replace(tmp, dest)
        return True
    if os.path.isfile(tmp):
        os.remove(tmp)   # our own empty partial download, nothing of the user's
    return False


def check_sfx():
    sfx = os.path.join(skillenv.SKILL_DIR, 'assets', 'hyperframes', 'assets', 'sfx')
    os.makedirs(sfx, exist_ok=True)

    def have(n):
        p = os.path.join(sfx, n + '.mp3')
        return os.path.isfile(p) and os.path.getsize(p) > 0

    home = os.path.expanduser('~')
    for lib in (os.path.join(home, '.claude', 'skills', 'media-use', 'audio', 'assets', 'sfx'),
                os.path.join(home, '.agents', 'skills', 'media-use', 'audio', 'assets', 'sfx')):
        for n in SFX_NAMES:
            src = os.path.join(lib, n + '.mp3')
            if not have(n) and os.path.isfile(src):
                shutil.copyfile(src, os.path.join(sfx, n + '.mp3'))
    # not found locally: fetch them from the HyperFrames repo, which publishes this Pixabay-licensed pack
    for n in SFX_NAMES:
        if not have(n):
            fetch(f'{SFX_URL}/{n}.mp3', os.path.join(sfx, n + '.mp3'))
    missing = [n for n in SFX_NAMES if not have(n)]
    if not missing:
        say('STATUS sound effects OK')
    else:
        say(f"STATUS sound effects MISSING: {' '.join(missing)} -> optional. Download similar free SFX from https://pixabay.com/sound-effects/")
        say(f'        and save them as {os.path.join(sfx, "<name>.mp3")}, then re-run this script.')
    return not missing


EDITS_URL = os.environ.get('EDITS_MCP_URL', 'http://127.0.0.1:19501/mcp')


def check_edits(osn):
    """Edits desktop exists only on macOS (Apple silicon). The automation server answers 401/403 without a token,
    which is the expected 'it is up' reply here: setup never reads or sends the token."""
    if osn != 'macos':
        say('STATUS edits MISSING -> Instagram Edits desktop only runs on macOS with Apple silicon. This edition of the'
            ' skill cannot edit on this machine.')
        return {'app': False, 'server': False}
    app = any(os.path.isdir(p) for p in ('/Applications/Edits.app',
                                         os.path.join(os.path.expanduser('~'), 'Applications', 'Edits.app')))
    server = False
    try:
        urllib.request.urlopen(urllib.request.Request(EDITS_URL, method='GET'), timeout=3)
        server = True
    except urllib.error.HTTPError:
        server = True          # 401/403/405: something is listening and refusing us, as expected without a token
    except Exception:
        server = False
    if not app:
        say('STATUS edits MISSING -> install Edits for Mac (free) from https://edits.instagram.com/desktop and sign in')
    elif not server:
        say('STATUS edits automation server OFF -> open Edits, Settings > Automation > Enable Automation Server, keep'
            ' Edits open, then re-run this script')
    else:
        say(f'STATUS edits OK (automation server answering at {EDITS_URL})')
    return {'app': app, 'server': server}


def alpha_codecs(ffmpeg):
    out = subprocess.run([ffmpeg, '-hide_banner', '-encoders'], **skillenv.TEXT).stdout if ffmpeg else ''
    have = {line.split()[1] for line in out.splitlines() if line.startswith(' ') and len(line.split()) > 1}
    codecs = [c for c, enc in (('hevc', 'hevc_videotoolbox'), ('prores', 'prores_ks')) if enc in have]
    say(f"STATUS alpha layers can be written as: {', '.join(codecs) or 'NOTHING (ffmpeg without prores_ks)'}")
    return codecs


# ------------------------------------------------------------------ main
def main():
    skillenv.utf8_stdio()
    info = skillenv.detect()
    osn = info['os']
    provider = skillenv.cutout_provider(info)
    how = 'Apple GPU / Neural Engine' if provider == 'CoreML' else 'no GPU acceleration, speed depends on the processor'
    say(f'STATUS system {skillenv.os_label(info)} | background cutout runs on {provider} ({how})')

    ff_ok, ffmpeg, ffprobe = check_ffmpeg(osn)
    node_ok, node, node_ver, npx = check_node(osn)
    py_ok, py = check_python(info)
    sfx_ok = check_sfx()
    edits = check_edits(osn)
    codecs = alpha_codecs(ffmpeg if ff_ok else None)
    ready = ff_ok and node_ok and py_ok

    sp = skillenv.shell_path
    record = {
        'schema': skillenv.SCHEMA,
        'ready': ready,
        'checked': datetime.date.today().isoformat(),
        'os': osn, 'wsl': info['wsl'], 'arch': info['arch'], 'python_arch': info['python_arch'],
        'skill_dir': sp(skillenv.SKILL_DIR),
        'python': sp(py) if py_ok else None,                       # PY in SKILL.md
        'hf': [sp(py), sp(os.path.join(skillenv.SKILL_DIR, 'scripts', 'hf.py'))] if py_ok else None,   # HF in SKILL.md
        'ffmpeg': sp(ffmpeg), 'ffprobe': sp(ffprobe),
        'node': sp(node) if node_ok else None, 'node_version': node_ver or None,
        'npx': [sp(p) for p in npx] if npx else None,
        'hyperframes': skillenv.HYPERFRAMES,
        'cutout': provider,
        'sfx': sfx_ok,
        'edits': edits,                                            # app installed / automation server answering
        'alpha_codecs': codecs,                                    # for matte.py / alphamov.py --codec
    }
    with open(skillenv.PLATFORM_FILE, 'w', encoding='utf-8') as f:
        json.dump(record, f, indent=1)
        f.write('\n')
    say('READY' if ready else 'NOT READY')
    return 0 if ready else 1


if __name__ == '__main__':
    sys.exit(main())
