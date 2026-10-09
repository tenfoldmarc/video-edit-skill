# Gotchas (each one cost a render)

## Timing / sync
- ffmpeg concat -> 0.033s video start offset + VFR gaps -> remove-background outputs extra frames -> the cutout drifts
  (by 20s it lagged a few frames: two copies of the speaker on screen after a cut). assemble.py re-encodes with
  `setpts=N/30/TB -fps_mode cfr`; cutout.py asserts equal frame counts.
- `tl.set` at a rounded time fires one frame late: use `frame/30 - 0.002`.
- `hyperframes snapshot` seeks approximately at cut boundaries; it can show the next shot a frame early. Only frames
  extracted from the final render (`check_cuts.py`) prove a cut.
- When a segment's in-point is trimmed, every hard-coded word time after it shifts. Keep a `SHIFT` derived from
  segments.json and wrap later times in `S(t)` (see template) instead of retyping them.
- Whisper word starts can be ~0.1-0.3s off and it hallucinates a leading word at a cut. Confirm pauses with
  `silencedetect` (n=-40dB, d=0.08) before trimming dead air.

## Rendering
- CSS `-webkit-mask-image` does not survive the renderer. Bake alpha into a VP9 WebM with ffmpeg alphamerge instead.
- `autoAlpha:1` sets opacity to 1 and overrides a CSS `opacity` on the same element. A "3% grain" layer shown with
  autoAlpha ran at 100%. Put low opacity on an inner element or tween opacity to the target value.
- Every `<video>` needs an `id` or it renders frozen. Each overlapping media element needs its own `data-track-index`.
  `<audio>` SFX need ids too, and overlapping SFX need separate track indices (the template's lane allocator does it).
- Never tween autoAlpha/opacity on an element that has data-start (the framework forces opacity 1 on active clips):
  wrap it in a plain div and animate the wrapper.
- Lint rejects tweening letterSpacing (layout snapping): fake tracking with scaleX.
- Element ids cannot contain apostrophes ("i've" broke the whole inline script). Use keys like 'ive'.
- `fromTo` renders its from-state immediately: pass `immediateRender:false` for anything hidden until its time.
- Heavy backdrop-filter/blur on many elements can make captures go black; keep it to a few.

## Assets / tools
- Node 22+ for HyperFrames, pinned `hyperframes@0.8.34`. Start it with `HF` (`PY "SK/scripts/hf.py" <command>`): it
  puts a Node 22+ first on PATH on any OS (an nvm default of Node 20 otherwise gives "HyperFrames requires Node.js >= 22").
- Python scripts run in the skill's own venv. Its path differs per OS (`.venv/bin/python` on Mac and Linux,
  `.venv/Scripts/python.exe` on Windows), so read `python` from `SK/.platform.json` instead of typing it.
  The first transcription downloads the Whisper model (small.en ~0.5GB, medium.en ~1.5GB).
- Transcription dies with `open() got an unexpected keyword argument 'metadata_errors'`: the venv has PyAV 19, which
  faster-whisper 1.2.1 does not support. Run `scripts/setup.py` again (or the old `scripts/setup.sh`, which calls it);
  it pins `av<19` and repairs the venv.
- zsh: `for x in "a b"; do set -- $x` does not split; use `${=x}` or a Python loop.
- If a shell safety hook blocks inline heredoc scripts or moves into the Trash, write the script to a file and run
  it; download temp files into a scratch folder instead of moving things around. Never delete the user's files.
- Large file uploads to chat can fail: deliver a 720p crf 26-28 phone copy and keep the full render on disk.
- Pinterest/Instagram pages block logged-out browsing; curl the page HTML or use Apify.

## Windows (same skill, different shell)
- Claude Code on Windows runs commands in Git Bash when Git for Windows is installed, otherwise in PowerShell, and
  both can be available at once. Write commands that work in both: full paths in double quotes with forward
  slashes, one command per call, no `&&`, no `VAR=1 cmd`, no `~` in arguments. In PowerShell start a quoted program
  with `&`: `& "PY" "SK/scripts/assemble.py" "<project>"`.
- `python3` is usually a Microsoft Store stub ("Python was not found"). Use `PY` for everything. Before the venv
  exists, try `python`, then `py -3`.
- A program installed while Claude Code is open is not found until Claude Code is fully quit and reopened (it keeps
  the PATH it started with). setup.py says so when it sees ffmpeg installed but not visible.
- `npx` is `npx.cmd` there: Python cannot start it by bare name. `HF` and cutout.py start it through node directly.
- The background cutout has no GPU path on Windows (HyperFrames uses CoreML on Apple Silicon only, CUDA only with
  `HYPERFRAMES_CUDA=1` and a CUDA build of onnxruntime), so it runs on the CPU. Run it in the background.
- Windows opens text files as cp1252 unless told otherwise: every `open()` in build.py needs `encoding='utf-8'`,
  or accents, curly quotes and emoji in captions come out broken (the page says charset UTF-8).
- File paths inside an ffmpeg FILTER (subtitles=, movie=, a fonts file) need the drive colon and backslashes
  escaped (`C\:/Users/...`). Pass files with `-i` instead; the skill's scripts never put a path in a filter, and the
  concat list holds bare file names only.
- Git Bash rewrites arguments that start with `/` into Windows paths. Fine for file paths; for anything else
  (a `/flag`) set `MSYS_NO_PATHCONV=1` for that command.
- Smart App Control (Windows 11) can block the unsigned image library (sharp) that HyperFrames loads for snapshots
  (the cutout loads the same library); antivirus can make ffmpeg fail once with `spawn EBUSY`. Retry once, then
  tell the user what Windows blocked.
- Transcription dies with `Library cublas64_12.dll is not found or cannot be loaded`: the PC has an NVIDIA card, so
  Whisper's default device ('auto') chose CUDA, but the CUDA toolkit is not installed. The scripts pass
  `device='cpu'`; do the same in any one-off `WhisperModel(...)` call (a re-transcribed snippet, for example).
- Windows on ARM (Snapdragon): the transcription engine has no ARM build; setup.py asks for the x64 Python.
