# Edits adapter

How to drive Instagram Edits for Mac through its MCP automation server. The server is undocumented and Meta ships
weekly, so this file describes behaviour and process, not tool names. Tool names and probe results live in
`SK/edits-capabilities.json`, written by discovery.

## Topology and install

```
Claude Code ──stdio──▶ insta-edits bridge ──HTTP──▶ Edits for Mac (127.0.0.1:19501/mcp)
```

- Edits: Settings > Automation > Enable Automation Server, copy the access token, keep Edits open.
- Bridge (recommended, plugin): `/plugin marketplace add faisalkhanzemi/insta-edits-for-claude` then
  `/plugin install insta-edits@insta-edits` (asks for the token, keeps it in the keychain), restart Claude Code.
  CLI alternative: `pipx install insta-edits`, `insta-edits set-token`, `claude mcp add --scope user edits -- insta-edits serve`.
  Never put the token on a command line or in `~/.claude.json`.
- Why the bridge: Edits offers ~32 tools on its home screen and ~274 with a project open, announces tool-list
  changes but never sends them. The bridge re-lists after each call and tells Claude. Without it Claude never sees
  the editor.
- Not official: the bridge is an independent open-source project (MIT). Edits is Meta's.

## Discovery (first run, and whenever Edits' version or schema changes)

Work in a throwaway project named `video-edit-discovery`, never in a user project.

1. Home screen: list tools, note project, import and catalog tools.
2. Create the throwaway project, import one short 9:16 clip from `~/Movies`, wait for the tool list to change, list
   again.
3. Classify every tool into buckets, recording exact name and input schema:
   `project.open/create/list`, `media.import`, `timeline.read`, `clip.add/trim/move/remove/duplicate`,
   `clip.transform` (scale, position, keyframes), `overlay/track` (stacking a second video above the base),
   `speed`, `transition`, `color/lut`, `text.add/style/animate`, `captions.generate/read/edit`, `audio.add/volume`,
   `effects`, `segmentation/cutout`, `preview.frame`, `export`, `share`.
4. Probe, do not guess. Each probe ends with a preview frame (or a short export) that Claude looks at:
   - **Coordinates**: text at (0.5, 0.5) and (0.1, 0.1): origin, range, and what the position anchors (centre,
     top-left, baseline) for text. Record the anchor; layout.md's formula is written for the baseline.
   - **Time**: seconds, ms or frames; timeline frame rate; whether trims snap to frames.
   - **Stable ids**: can clips, texts and overlays carry a name or metadata field? (Needed by reconcile.)
   - **Captions**: word-level or segment-level timings; can a caption's text be edited in place?
   - **Segmentation**: if a cutout/segmentation tool exists, apply it to a duplicated clip on an upper track with a
     text between the two. Speaker in front of the text = path 1 in SKILL.md step 4.
   - **Alpha layers**: generate a 2 s test layer (`alphamov.py` on any transparent WebM, once with `--codec prores`,
     once with `--codec hevc` if setup lists it), import each, put it above the base with a text between. Pass =
     the base and the text show through the transparent area in the preview frame. Record which codecs pass.
   - **Overlay geometry**: does a video on an upper track fill the canvas like the base clip (same fit), and does the
     same transform (scale/position) produce the same framing on both? Test with the base clip duplicated onto the
     upper track and a 1.6x zoom on both: the preview must show no double edge.
   - **Export**: export the throwaway project to `~/Movies/...`; confirm resolution, fps and that audio is present.
5. Mark `share`/publish/schedule tools **forbidden without explicit per-video approval**.
6. Delete the throwaway project (Claude's own, not the user's).
7. Write `edits-capabilities.json`:
   ```json
   {"editsVersion": "454.0.0", "schema": "2026.10.19-1", "probed": "YYYY-MM-DD",
    "coords": {"origin": "top-left", "range": [0, 1], "textAnchor": "center"},
    "time": {"unit": "seconds", "fps": 30, "snaps": true},
    "stableIds": "clip.name",
    "captions": {"timings": "word", "editable": true},
    "behindHead": "segmentation | alpha-layer | none",
    "alphaCodecs": ["hevc", "prores"],
    "overlayFillsLikeBase": true,
    "tools": {"media.import": "<name>", "clip.transform": "<name>", "...": "..."},
    "forbidden": ["<share tool names>"],
    "gaps": ["..."]}
   ```

## Layer stacking (behind-head words and inserts)

Bottom to top, per segment:
1. base clip (the take, with the segment's zoom/cx/cy as an Edits transform)
2. `behind` texts and `behind` inserts
3. speaker layer: Edits' own segmentation of a duplicate of the base (path 1), or `layers.json[seg].file` (path 2)
4. `front` texts, captions, `front` inserts

Speaker layer rules (path 2):
- Start = the base segment's start on the timeline, duration = its duration, same transform as the base. The layer
  is the source frame (same aspect, no crop), so an identical transform keeps it aligned; never position it by eye.
- No audio on the layer track.
- If the base segment is trimmed, the EDL changes, `matte.py` makes a new layer (new key) and reconcile replaces the
  old one. Never trim a layer in Edits to "match".
- If `overlayFillsLikeBase` is false, stop and report: the alignment rule above does not hold in this build.

## Reconcile contract

- Desired: `edl.json` + `media.json` + `layers.json`. Actual: whatever `timeline.read` returns.
- Every EDL item writes its id into the Edits object (name/metadata): segments `seg:<id>`, speaker layers
  `layer:<id>:<key>`, texts `txt:<id>`, inserts `ins:<id>`, audio `sfx:<id>`. No such field: match by (track, start,
  source file) and warn that reconcile is weaker.
- Absolute times are computed from the segment order: segment start = sum of previous segment durations; a
  text/insert/SFX at `at` sits at segment start + `at`.
- Apply order: clip timing -> transforms -> speaker layers -> grade -> captions and texts -> inserts -> audio.
- After applying, read back and assert: times within one frame, positions within 0.01. Retry only mismatches.
- A reconcile with no diff makes zero mutating calls.

## Known traps

| Trap | Handling |
|---|---|
| `~` not expanded | Always absolute paths (media.json has them). |
| Sandbox refuses `~/Downloads`, `~/Desktop`, temp dirs | Project under `~/Movies`; `stage.py` copies media in. |
| Library songs export silent through automation | Never rely on them (hard rule 8). |
| Song by track id adds the wrong song | If music is used at all, pass the exact title and verify on the timeline. |
| Tool set changes with the screen | After opening a project, wait for the refreshed list before editor calls. |
| HTTP 401/403 | Token rotated in Edits: `/plugin configure insta-edits@insta-edits` or `insta-edits set-token`. |
| VP9 WebM with alpha | macOS does not decode its alpha: always convert (`matte.py` and `alphamov.py` do). |
| Weekly server changes | Version-stamped capability map; a missing mapped tool means re-run discovery, then fail. |
| Bug in the bridge | `insta-edits doctor --json` (contains no token) and open an issue on its repo. |
