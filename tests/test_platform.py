#!/usr/bin/env python3
"""Cross-platform logic tests. Standard library only:   python3 tests/test_platform.py

These simulate Windows (and Linux / WSL) on whatever machine runs them: path building, tool lookup folders, how npx
is started, PATH handling, escaping. They do NOT prove the skill runs on Windows; only a real Windows machine does.
"""
import json
import ntpath
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import layerkit  # noqa: E402
import matte  # noqa: E402
import setup  # noqa: E402
import skillenv  # noqa: E402

WIN_HOME = 'C:\\Users\\Pat Smith'
WIN_SKILL = WIN_HOME + '\\.claude\\skills\\video-edit'
WIN_ENV = {'LOCALAPPDATA': WIN_HOME + '\\AppData\\Local', 'ProgramFiles': 'C:\\Program Files'}


class Detect(unittest.TestCase):
    def test_os_names(self):
        self.assertEqual(skillenv.os_name('Darwin', '25.6.0', {}), ('macos', False))
        self.assertEqual(skillenv.os_name('Windows', '11', {}), ('windows', False))
        self.assertEqual(skillenv.os_name('Linux', '6.8.0-45-generic', {}), ('linux', False))

    def test_wsl_is_linux_flavor(self):
        self.assertEqual(skillenv.os_name('Linux', '5.15.153.1-microsoft-standard-WSL2', {}), ('linux', True))
        self.assertEqual(skillenv.os_name('Linux', '6.1.0', {'WSL_DISTRO_NAME': 'Ubuntu'}), ('linux', True))

    def test_git_bash_python_counts_as_windows(self):
        self.assertEqual(skillenv.os_name('MINGW64_NT-10.0-22631', '3.4.10', {})[0], 'windows')
        self.assertEqual(skillenv.os_name('MSYS_NT-10.0-19045', '3.4.10', {})[0], 'windows')

    def test_arch(self):
        for raw, want in (('arm64', 'arm64'), ('aarch64', 'arm64'), ('ARM64', 'arm64'), ('x86_64', 'x64'),
                          ('AMD64', 'x64'), ('i686', 'x86'), ('', 'unknown')):
            self.assertEqual(skillenv.norm_arch(raw), want)

    def test_x64_python_on_windows_arm_machine(self):
        env = {'PROCESSOR_IDENTIFIER': 'ARMv8 (64-bit) Family 8 Model 1 Revision 201, Qualcomm Technologies Inc'}
        self.assertEqual(skillenv.machine_arch('windows', 'x64', env), 'arm64')
        self.assertEqual(skillenv.machine_arch('windows', 'x64', {'PROCESSOR_IDENTIFIER': 'Intel64 Family 6'}), 'x64')

    def test_rosetta_python_on_apple_silicon(self):
        self.assertEqual(skillenv.machine_arch('macos', 'x64', {}, sysctl='1\n'), 'arm64')
        self.assertEqual(skillenv.machine_arch('macos', 'x64', {}, sysctl=''), 'x64')

    def test_cutout_provider(self):
        self.assertEqual(skillenv.cutout_provider({'os': 'macos', 'arch': 'arm64'}), 'CoreML')
        for osn, arch in (('macos', 'x64'), ('windows', 'x64'), ('windows', 'arm64'), ('linux', 'x64')):
            self.assertEqual(skillenv.cutout_provider({'os': osn, 'arch': arch}), 'CPU')

    def test_labels(self):
        self.assertEqual(skillenv.os_label({'os': 'macos', 'arch': 'arm64', 'wsl': False}), 'macOS arm64 (Apple Silicon)')
        self.assertEqual(skillenv.os_label({'os': 'windows', 'arch': 'x64', 'wsl': False}), 'Windows x64')
        self.assertEqual(skillenv.os_label({'os': 'linux', 'arch': 'x64', 'wsl': True}), 'Linux (WSL on Windows) x64')


class Paths(unittest.TestCase):
    def test_venv_python_per_os(self):
        self.assertEqual(skillenv.venv_python(WIN_SKILL, 'windows'), WIN_SKILL + '\\.venv\\Scripts\\python.exe')
        self.assertEqual(skillenv.venv_python('/Users/pat/.claude/skills/video-edit', 'macos'),
                         '/Users/pat/.claude/skills/video-edit/.venv/bin/python')
        self.assertEqual(skillenv.venv_python('/home/pat/.claude/skills/video-edit', 'linux'),
                         '/home/pat/.claude/skills/video-edit/.venv/bin/python')

    def test_find_venv_python_takes_what_exists(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(skillenv.find_venv_python(d, 'windows'))
            scripts = os.path.join(d, '.venv', 'Scripts')
            os.makedirs(scripts)
            open(os.path.join(scripts, 'python.exe'), 'w').close()
            self.assertEqual(skillenv.find_venv_python(d, 'macos'), os.path.join(scripts, 'python.exe'))

    def test_shell_path_is_paste_safe(self):
        p = skillenv.shell_path(skillenv.venv_python(WIN_SKILL, 'windows'))
        self.assertEqual(p, 'C:/Users/Pat Smith/.claude/skills/video-edit/.venv/Scripts/python.exe')
        self.assertNotIn('\\', p)
        self.assertEqual(json.loads(json.dumps({'python': p}))['python'], p)   # no escaping surprises in the json
        self.assertEqual(skillenv.shell_path('/Users/pat/x'), '/Users/pat/x')
        self.assertIsNone(skillenv.shell_path(None))

    def test_path_arg_expands_tilde(self):
        self.assertEqual(skillenv.path_arg('~/reel-edits/x'), os.path.join(os.path.expanduser('~'), 'reel-edits', 'x'))
        self.assertFalse(skillenv.path_arg('~').startswith('~'))

    def test_safe_name(self):
        self.assertEqual(skillenv.safe_name('hook'), 'hook')
        self.assertEqual(skillenv.safe_name('cta: "follow"?'), 'cta___follow__')
        for ch in ':?*"<>|/\\':
            self.assertNotIn(ch, skillenv.safe_name(f'a{ch}b'))

    def test_concat_entry(self):
        self.assertEqual(skillenv.concat_entry('seg_0.mp4'), "file 'seg_0.mp4'\n")
        self.assertEqual(skillenv.concat_entry("it's.mp4"), "file 'it'\\''s.mp4'\n")
        self.assertNotIn('\\', skillenv.concat_entry('C:\\Users\\Pat\\work\\seg_0.mp4'))


class Tools(unittest.TestCase):
    def test_windows_fallback_dirs(self):
        dirs = skillenv.fallback_dirs('ffmpeg', 'windows', WIN_ENV, WIN_HOME)
        self.assertEqual(dirs[0], WIN_HOME + '\\AppData\\Local\\Microsoft\\WinGet\\Links')
        self.assertIn(WIN_HOME + '\\AppData\\Local\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg*\\*\\bin', dirs)
        self.assertIn('C:\\Program Files\\nodejs', skillenv.fallback_dirs('node', 'windows', WIN_ENV, WIN_HOME))
        self.assertNotIn('C:\\Program Files\\nodejs', dirs)
        self.assertFalse(any('/' in d for d in dirs))

    def test_windows_nvm_symlink(self):
        env = dict(WIN_ENV, NVM_SYMLINK='C:\\nvm4w\\nodejs')
        self.assertIn('C:\\nvm4w\\nodejs', skillenv.fallback_dirs('node', 'windows', env, WIN_HOME))

    def test_posix_fallback_dirs(self):
        mac = skillenv.fallback_dirs('node', 'macos', {}, '/Users/pat')
        self.assertEqual(mac[0], '/Users/pat/.nvm/versions/node/v*/bin')
        self.assertIn('/opt/homebrew/bin', mac)
        self.assertEqual(skillenv.fallback_dirs('ffmpeg', 'linux', {}, '/home/pat'), ['/usr/local/bin', '/usr/bin', '/snap/bin'])

    def test_node_major(self):
        self.assertEqual(skillenv.node_major('v22.23.2'), 22)
        self.assertEqual(skillenv.node_major('v20.20.2\n'), 20)
        self.assertEqual(skillenv.node_major('24.1.0'), 24)
        self.assertEqual(skillenv.node_major(''), 0)
        self.assertEqual(skillenv.node_major('Python was not found; run without arguments to install'), 0)

    def test_npx_on_windows_prefers_node_plus_cli_js(self):
        node = 'C:\\Program Files\\nodejs\\node.exe'
        cli = 'C:\\Program Files\\nodejs\\node_modules\\npm\\bin\\npx-cli.js'
        cmd = 'C:\\Program Files\\nodejs\\npx.cmd'
        self.assertEqual(skillenv.npx_command(node, 'windows', exists=lambda p: p in (cli, cmd)), [node, cli])

    def test_npx_on_windows_falls_back_to_full_cmd_path(self):
        node = 'C:\\nvm4w\\nodejs\\node.exe'
        cmd = 'C:\\nvm4w\\nodejs\\npx.cmd'
        got = skillenv.npx_command(node, 'windows', exists=lambda p: p == cmd)
        self.assertEqual(got, [cmd])
        self.assertTrue(ntpath.isabs(got[0]) and got[0].lower().endswith('.cmd'))   # never the bare name "npx"

    def test_npx_on_posix(self):
        node = '/Users/pat/.nvm/versions/node/v22.23.2/bin/node'
        self.assertEqual(skillenv.npx_command(node, 'macos', exists=lambda p: True),
                         ['/Users/pat/.nvm/versions/node/v22.23.2/bin/npx'])
        self.assertIsNone(skillenv.npx_command(None, 'macos'))

    def test_hyperframes_env_windows(self):
        env = {'Path': 'C:\\Windows\\system32;C:\\Old\\nodejs', 'USERNAME': 'pat'}
        out = skillenv.hyperframes_env('C:\\Program Files\\nodejs\\node.exe', 'C:\\ff\\bin\\ffmpeg.exe', env,
                                       pathsep=';', dirname=ntpath.dirname)
        self.assertEqual(out['Path'], 'C:\\Program Files\\nodejs;C:\\ff\\bin;C:\\Windows\\system32;C:\\Old\\nodejs')
        self.assertNotIn('PATH', out)                       # no second, differently-cased PATH variable
        self.assertEqual(out['HYPERFRAMES_NO_TELEMETRY'], '1')
        self.assertEqual(env['Path'], 'C:\\Windows\\system32;C:\\Old\\nodejs')   # caller's environment untouched

    def test_hyperframes_env_moves_chosen_node_in_front_of_older_one(self):
        env = {'PATH': '/Users/pat/.nvm/versions/node/v20.20.2/bin:/usr/bin:/Users/pat/.nvm/versions/node/v22.23.2/bin'}
        out = skillenv.hyperframes_env('/Users/pat/.nvm/versions/node/v22.23.2/bin/node', None, env, pathsep=':')
        self.assertEqual(out['PATH'], '/Users/pat/.nvm/versions/node/v22.23.2/bin:/Users/pat/.nvm/versions/node/v20.20.2/bin:/usr/bin')

    def test_hyperframes_env_keeps_users_telemetry_choice(self):
        out = skillenv.hyperframes_env(None, None, {'PATH': '/usr/bin', 'HYPERFRAMES_NO_TELEMETRY': '0'}, pathsep=':')
        self.assertEqual(out['HYPERFRAMES_NO_TELEMETRY'], '0')


class Setup(unittest.TestCase):
    def test_fix_is_per_os(self):
        self.assertEqual(setup.fix('ffmpeg', 'macos'), 'brew install ffmpeg')
        self.assertEqual(setup.fix('ffmpeg', 'linux'), 'sudo apt install ffmpeg')
        self.assertTrue(setup.fix('ffmpeg', 'windows').startswith('winget install --id Gyan.FFmpeg -e'))
        self.assertTrue(setup.fix('node', 'windows').startswith('winget install --id OpenJS.NodeJS.LTS -e'))
        self.assertTrue(setup.fix('python', 'windows').startswith('winget install --id Python.Python.3.12 -e'))
        self.assertIn('python3-venv', setup.fix('venv', 'linux'))

    def test_windows_fixes_say_restart_and_never_brew(self):
        for what in ('ffmpeg', 'node', 'python', 'venv'):
            f = setup.fix(what, 'windows')
            self.assertIn('reopen', f)
            self.assertNotIn('brew', f)
            self.assertNotIn('apt', f)

    def test_requirements_are_the_hotfix_pins(self):
        self.assertEqual(setup.REQUIREMENTS, ['faster-whisper==1.2.1', 'av>=11,<19', 'pillow'])

    def test_python_39_is_not_refused(self):
        self.assertEqual(skillenv.OLDEST_PY, (3, 9))   # system Python on many Macs; the old setup.sh accepted it


@unittest.skipIf(os.name == 'nt', 'nvm (the shell tool) is macOS / Linux only')
class NvmParity(unittest.TestCase):
    """The old zsh scripts ran `nvm use 22`. Mac users with nvm must get that same Node, whatever their default is."""

    def fake_node(self, home, version):
        d = os.path.join(home, '.nvm', 'versions', 'node', 'v' + version, 'bin')
        os.makedirs(d)
        p = os.path.join(d, 'node')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(f'#!/bin/sh\necho v{version}\n')
        os.chmod(p, 0o755)
        return p

    def test_newest_nvm_22_is_picked(self):
        with tempfile.TemporaryDirectory() as home:
            self.fake_node(home, '20.20.2')
            self.fake_node(home, '22.3.0')
            want = self.fake_node(home, '22.23.2')
            self.fake_node(home, '24.1.0')
            self.assertEqual(skillenv.nvm_node22({}, home), (want, 'v22.23.2'))
            node, ver, _ = skillenv.find_node('macos', {}, home)
            self.assertEqual((node, ver), (want, 'v22.23.2'))

    def test_no_nvm_22_means_no_override(self):
        with tempfile.TemporaryDirectory() as home:
            self.fake_node(home, '20.20.2')
            self.assertEqual(skillenv.nvm_node22({}, home), (None, ''))

    def test_sfx_list(self):
        self.assertEqual(len(setup.SFX_NAMES), 6)
        self.assertTrue(setup.SFX_URL.startswith('https://raw.githubusercontent.com/heygen-com/hyperframes/'))


class Cutout(unittest.TestCase):
    def test_spinner_output_is_split_into_lines(self):
        s = ('\x1b[?25l\x1b[2K\x1b[1G\u25d0  Loading model on CPU\x1b[2K\x1b[1G\u25d3  Frame 1/132 (0%) \u2014 645ms/frame avg'
             '\x1b[2K\x1b[1G\u25c7  Removed background from 132 frames in 54.7s (2.4 fps, CPU) \u2192 C:\\x\\subject.webm\r\n')
        lines, rest = layerkit.split_progress(s)
        self.assertEqual(lines[0], 'Loading model on CPU')
        self.assertTrue(lines[1].startswith('Frame 1/132'))
        self.assertTrue(lines[2].startswith('Removed background from 132 frames'))
        self.assertEqual(rest, '')

    def test_unfinished_line_is_kept_for_next_chunk(self):
        lines, rest = layerkit.split_progress('Frame 1/132\nFrame 2/1')
        self.assertEqual((lines, rest), (['Frame 1/132'], 'Frame 2/1'))


class MatteGeometry(unittest.TestCase):
    def test_layer_size_keeps_aspect_and_caps_by_zoom(self):
        self.assertEqual(matte.layer_size(2160, 3840, 1.0), (1080, 1920))
        self.assertEqual(matte.layer_size(2160, 3840, 1.9), (2052, 3648))
        self.assertEqual(matte.layer_size(1080, 1920, 1.9), (1080, 1920))   # never upscale

    def test_canvas_mapping_matches_the_edl_zoom_rule(self):
        self.assertAlmostEqual(matte.to_canvas(0.3, 1.0, 0.2), 0.3)          # no zoom: centre ignored
        self.assertAlmostEqual(matte.to_canvas(0.5, 2.0, 0.5), 0.5)
        self.assertAlmostEqual(matte.to_canvas(0.25, 2.0, 0.5), 0.0)
        self.assertAlmostEqual(matte.to_canvas(0.25, 2.0, 0.1), 0.5)         # centre clamped to 0.25 at 2x

    def test_behind_segments_come_from_texts(self):
        edl = {'texts': [{'segment': 'a', 'layer': 'behind'}, {'segment': 'b'}, {'segment': 'a', 'layer': 'behind'},
                         {'segment': 'c', 'layer': 'behind'}]}
        self.assertEqual(matte.behind_segments(edl), ['a', 'c'])

    def test_cache_key_changes_with_trim(self):
        with tempfile.NamedTemporaryFile(delete=False) as fh:
            fh.write(b'x')
        try:
            k1 = matte.cache_key(fh.name, {'in': 1.0, 'out': 2.0}, 1080, 'prores')
            self.assertEqual(k1, matte.cache_key(fh.name, {'in': 1.0, 'out': 2.0}, 1080, 'prores'))
            self.assertNotEqual(k1, matte.cache_key(fh.name, {'in': 1.0, 'out': 2.1}, 1080, 'prores'))
            self.assertNotEqual(k1, matte.cache_key(fh.name, {'in': 1.0, 'out': 2.0}, 1080, 'hevc'))
        finally:
            os.remove(fh.name)

    def test_alpha_args(self):
        self.assertIn('yuva444p10le', layerkit.alpha_args('prores'))
        self.assertIn('hevc_videotoolbox', layerkit.alpha_args('hevc'))
        with self.assertRaises(ValueError):
            layerkit.alpha_args('vp9')


class NoPosixOnlyCode(unittest.TestCase):
    """Guards against the Windows breaks this skill had: shell strings, POSIX temp paths, default-encoding files."""
    FILES = [os.path.join(ROOT, 'scripts', f) for f in sorted(os.listdir(os.path.join(ROOT, 'scripts'))) if f.endswith('.py')] + [
        os.path.join(ROOT, 'assets', 'overlay-examples', 'claude-desktop', 'build.py'),
        os.path.join(ROOT, 'assets', 'overlay-examples', 'skill-md', 'build.py')]

    def src(self, f):
        with open(f, encoding='utf-8') as fh:
            return fh.read()

    def test_no_shell_or_posix_paths(self):
        for f in self.FILES:
            s = self.src(f)
            for bad in ('shell=True', 'os.system(', '/dev/null', "'/tmp", '"/tmp', '.venv/bin/python'):
                self.assertFalse(bad in s, f'{bad!r} in {f}')

    def test_every_text_open_names_utf8(self):
        for f in self.FILES:
            for call in re.findall(r'(?<![\w.])open\(([^\n]*)', self.src(f)):
                if "'wb'" in call or "'rb'" in call:
                    continue
                self.assertTrue("encoding='utf-8'" in call, f'open() without utf-8 in {f}: open({call}')

    def test_no_subprocess_text_mode_with_locale_encoding(self):
        for f in self.FILES:
            self.assertFalse('text=True' in self.src(f), f'text=True (cp1252 on Windows) in {f}')

    def test_no_program_started_by_bare_name(self):
        """subprocess.run(['npx', ...]) cannot start npx.cmd on Windows; tools go through skillenv / shutil.which."""
        pat = re.compile(r'''(?:run|Popen|call|check_output)\(\s*\[\s*['"](npx|npm|node|ffmpeg|ffprobe)['"]''')
        for f in self.FILES:
            m = pat.search(self.src(f))
            self.assertIsNone(m, f'{m.group(0) if m else ""} started by bare name in {f}')


if __name__ == '__main__':
    unittest.main(verbosity=1)
