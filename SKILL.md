---
name: video-edit
description: "Turns raw 9:16 talking-head clips into a finished Instagram reel inside Instagram Edits for Mac, driven through its MCP automation server. Claude does the creative and analytical work (takes, cut points, look, caption copy, layout, QA); Edits does the editing (timeline, cuts, punch-ins, grade, text, captions, audio, export). For the effects Edits cannot do, such as words behind the speaker's head or animated UI inserts, the skill generates only that layer (a speaker cutout or an insert with alpha) and Edits composites it. Trigger with /video-edit or phrases like 'edit these clips', 'I dropped clips in my downloads', 'cut this into a reel', 'make this reel look fire'."
---

# /video-edit (Instagram Edits edition)

Raw clips in, finished reel out, in an Edits project the user can open and touch by hand. Notes from the user
become changes to `edl.json`, and the skill reconciles the Edits timeline to it: a re-run with an unchanged EDL
changes nothing, a note like "cut the pause before X" touches one segment.

## Who does what (the core rule)

| Claude (analysis and art direction) | Edits (all editing) | Generated layers (only when Edits can't) |
|---|---|---|
| Contact sheets, transcripts, speech map | Import, timeline, clip order and trims | Speaker cutout with alpha, per segment, for words behind the head (`matte.py`) |
| Rebuilds the script, picks takes, cut points | Punch-ins (scale/position), transitions | Animated UI inserts with alpha (sub-agents + `alphamov.py`) |
| Look design, layout math, caption copy | Grade/LUT, text, captions, animations | |
| Where SFX go and how loud | Audio placement and volume | |
| QA of frames and audio | Preview frames, export, (posting, only by the user) | |

Claude never renders or encodes the reel. The only video files Claude writes are layers with alpha for one segment
or one insert, and the intermediates that produce them. Everything else is an ffprobe/ffmpeg read that ends in
JSON, text or a JPG to look at.

Read before building: `references/edits-adapter.md` (talking to Edits: bridge, discovery, layer stacking,
reconcile, traps), `references/layout.md` (safe zone and behind-head maths in Edits' normalised canvas),
`references/looks.md` (the three looks as design intent, mapped to what Edits offers), `references/gotchas.md`.
Read `references/overlays.md` only when the script calls for an animated insert.

macOS on Apple silicon only: Edits desktop exists nowhere else.

## Step 0: Setup

`SK` is this skill's folder (the one holding this SKILL.md), as a full path, usually `~/.claude/skills/video-edit`.

Every run: run `python3 "SK/scripts/setup.py"`, read the STATUS lines, then read `SK/.platform.json`.
- ffmpeg / node / python venv MISSING: give the exact fix the line ends with and stop until it prints READY.
- `edits` MISSING or automation server OFF: give the fix from the line and stop. Edits must stay open during the run.
- `alpha layers can be written as`: the codecs this ffmpeg can write (hevc needs VideoToolbox, prores always works).
- Sound effects MISSING is optional.

`PY` = the `python` value in `.platform.json` (the skill's venv: faster-whisper, Pillow). Run every script with it.

First run only (no `SK/config.json`):
1. Say: "Welcome to /video-edit! Let's get you set up. This takes a few minutes and only happens once."
2. Ask in one message: name, Instagram handle, default look (**bold**, **cool girl**, **cool dude**; offer bold if
   unsure), where raw clips land (default `~/Downloads`) and where projects live (default `~/Movies/reel-edits`;
   it must be under `~/Movies`, Edits' sandbox refuses the rest).
3. Check the MCP chain: the `edits` server must come through the `insta-edits` bridge (in `/mcp`; with the CLI,
   `insta-edits doctor` all green). Not there: give the install from the adapter and stop. A direct HTTP entry to
   127.0.0.1:19501 is not enough, Claude would never see the editor's tools.
4. Run discovery (adapter, "Discovery") and save `SK/edits-capabilities.json`. It decides, among other things,
   whether Edits does behind-head itself, whether it accepts alpha layers and in which codec.
5. Optional Apify for the user's own reels (orbit, profile insert): as in overlays.md. Without it, ask for files.
6. Save `SK/config.json` (no secrets, never the Edits token):
   ```json
   {"name": "...", "instagram": "handle-without-@", "defaultLook": "bold", "clipsDir": "~/Downloads",
    "projectsDir": "~/Movies/reel-edits", "setupComplete": true, "setupDate": "YYYY-MM-DD"}
   ```

Later runs: if Edits' app version or automation schema differs from `edits-capabilities.json`, or a mapped tool is
missing, re-run discovery before editing.

## Hard rules
1. Safe zone, in Edits' normalised canvas (0..1, origin top-left; confirmed by discovery): nothing above y 0.115 or
   below y 0.766, side margins 0.033, right margin 0.093 from y 0.602 down (IG action rail).
2. Never cover the face with text, cards or inserts. Behind-head words show at least ~70% of each letter.
3. Captions say what was actually said: fix mishearings ("Claude" -> "cloud"/"claws", "skill" -> "scale").
   No em dashes in on-screen text.
4. SFX subtle (0.75 of the base level), never louder than the voice; voice peaks around -2 to -5 dB on the export.
5. Credit other creators on screen (@handle) when their reels appear. Real numbers on the user's own profile only;
   anything else is a generic placeholder, never a real person, never fabricated proof.
6. Prove cuts and layer alignment from the exported file (`qa_export.py`), not from what a tool call claimed.
7. Never publish, share or schedule from Edits. The user posts from the Edits window. Only an explicit go-ahead
   for that specific video changes this.
8. No Edits library songs in automated exports (they export silent). Use the user's own audio, or leave the song
   to the user in the Edits window and say so.
9. Originals are read, never modified or deleted. Edits imports copies from `<project>/media/`.
10. Every change goes through `edl.json` and the reconcile loop. No ad-hoc timeline pokes.

## Workflow

### 1. Intake
- Clips: the files the user names, else the newest videos in `clipsDir`. Create `<projectsDir>/<slug>/` (absolute
  path, under `~/Movies`).
- Style references (reels, pins): look at their frames before designing anything (overlays.md says how to fetch).

### 2. Ingest and stage
```bash
PY SK/scripts/ingest.py <project> <clips or folder> [--newest 5]
PY SK/scripts/stage.py <project> --sfx whoosh-short,pop
```
Look at `work/sheets.jpg` (setups, angles), read `transcript.txt` (lines, word times, speech map). `stage.py` copies
clips and chosen SFX into `media/` and writes `media.json`, the only paths Edits imports from.

### 3. Pick takes and design -> `<project>/edl.json` (desired state)
- Rebuild the script from the takes; use the LAST complete clean take of each line unless the user says otherwise.
- In ~0.05-0.07 s before the first word, out at the silence start after the last word. Confirm short pauses with
  silencedetect (Whisper invents a leading word at cuts). Zero dead air between sections.
- Two segments in a row from the same angle: punch one in (zoom 1.3-1.9, centred on the chest).
- Unsure words (names, CTA keyword): re-transcribe that snippet with medium.en and a prompt holding the names.
- Look per section: `defaultLook`, and a line that names a look switches its section.
- Times of texts, inserts and SFX are relative to their segment's start, so trims never shift them by accident.
  ```json
  {"version": 1, "project": "<Edits project name or id>", "look": "bold",
   "segments": [{"id": "hook", "clip": "c1", "in": 12.66, "out": 15.72, "zoom": 1.0, "cx": 0.5, "cy": 0.45,
                 "look": "bold", "line": "Everybody is doing this wrong"}],
   "texts":    [{"id": "t-wrong", "segment": "hook", "words": "wrong", "at": 2.1, "dur": 0.9, "x": 0.5,
                 "y": 0.21, "size": 220, "style": "bold-big", "layer": "behind"}],
   "inserts":  [{"id": "ig", "file": "media/inserts/ig-follow.mov", "segment": "cta", "at": 0.3, "dur": 2.9,
                 "x": 0.5, "y": 0.62, "scale": 0.7, "layer": "front"}],
   "audio":    [{"id": "sfx1", "sfx": "pop", "segment": "hook", "at": 2.1, "gain": 0.75}]}
  ```
  `layer`: `front` (above the speaker) or `behind` (between the base clip and the speaker cutout).
- Post the EDL as a short table (line, clip, look, behind-head words) and keep going; do not wait.

### 4. Behind-head words and inserts (start as soon as the EDL is locked; run in the background)
Pick the path from `edits-capabilities.json` once, record it in `<project>/analysis.json`, tell the user if it is
not the first:
1. **Edits segments the speaker itself** (a cutout/segmentation tool exists): apply it to the duplicated segment
   in Edits. No generated layer.
2. **Edits accepts alpha video**: `PY SK/scripts/matte.py <project> [--codec hevc|prores]` cuts the speaker out of
   every segment with a `behind` item, straight from the original, and writes `media/layers/<id>-<key>.mov` +
   `layers.json` (frames checked, alpha checked, head position per segment). Cached by segment: a note round only
   re-cuts trimmed segments. One run at a time, ~7 s per second of footage.
3. **Neither**: move the word in front, beside the head or over the chest, and say the behind-head move is not
   possible with this Edits build.
Place behind-head words with `layers.json` -> `head.canvas_head_top` and the formula in layout.md. `head.moving`
true means the head moves during the segment: put that word in front instead.

Animated inserts: one sub-agent per insert with the brief in overlays.md (transparent WebM), then
`PY SK/scripts/alphamov.py <in.webm> <project>/media/inserts/<name>.mov --codec <codec>`. Keep building meanwhile.

### 5. Reconcile into Edits
Follow the adapter's reconcile contract: open or create the project, wait for the editor tools, import from
`media.json`/`layers.json`/inserts, read the timeline, diff by EDL ids, apply the diff in order (clip timing ->
transforms -> layers -> grade -> captions and texts -> audio), read back and assert.
- A speaker layer gets exactly the base segment's start, duration and transform (zoom/cx/cy). Stacking, bottom to
  top: base clip, `behind` texts/inserts, speaker layer, `front` texts, captions, `front` inserts.
- Captions: generate them in Edits, then overwrite every line with Claude's corrected copy; keep Edits' timing unless
  it crosses a word boundary.

### 6. Look
Edits does the pixels, Claude chooses: looks.md gives the intent per look and how to map it to Edits' grade
controls, LUTs, fonts and text animations listed in discovery. Hard cuts by default; punch-ins carry the variety.

### 7. Export and QA
- Export from Edits to `<project>/renders/<slug>-vN.mp4` (and a 720p copy if Edits offers it).
- `PY SK/scripts/qa_export.py <project> renders/<slug>-vN.mp4 --cuts <cut times read back from the timeline>
  --at <every behind-head word, text entry, insert>`. Look at `work/qa/cut_check.jpg` (each after-cut frame shows
  the new shot, no speaker layer from the previous shot) and every `at_*.jpg` (safe zone, face clear, behind-head
  letters readable, speaker layer aligned with the base: no double edge or halo).
- Audio line: max around -2 to -5 dB. Silent export with music on the timeline = rule 8.
- Fix through the EDL and reconcile again.

### 8. Deliver
Point to the export (and phone copy). Say in plain terms what changed since the last version, which path step 4
used, and anything that needs the user's call (music, posting). Keep every `edl.vN.json`; any version can be
rebuilt by reconciling to it. The reel is posted by the user from the Edits window.

## Defaults that came out of real feedback (do not re-litigate)
- Change the grade and captions to create a look; never replace the background with an AI-generated room.
- No film grain. Dark is fine, but keep the subject lit and skin from going red.
- Lead-in captions centred in front of the speaker read better than lines pinned to the left edge.
- Words behind the head are the signature move, but only when readable.

---
Original skill by [@tenfoldmarc](https://instagram.com/tenfoldmarc). This edition hands the editing to Instagram Edits for Mac.
