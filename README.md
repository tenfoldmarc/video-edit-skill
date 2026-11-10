# Video Edit, Instagram Edits edition
### A fork of [tenfoldmarc/video-edit-skill](https://github.com/tenfoldmarc/video-edit-skill) that edits inside Instagram Edits for Mac

Film your talking-head clips, drop them in a folder, type `/video-edit-insta-edits`. Claude picks your best take of every line, cuts the dead air and designs the look; **Instagram Edits does the editing** through its built-in MCP automation server. You end up with a normal Edits project you can open, tweak by hand and post from.

The original skill rendered the whole reel itself with HyperFrames. This edition only generates what Edits can't draw (the cutout of you that lets words sit behind your head, and animated UI inserts), as layers with alpha that Edits stacks on its own timeline.

---

## How the work is split

| Claude | Instagram Edits | Generated layers |
|---|---|---|
| Contact sheets and word-level transcripts of every take | Import, timeline, cuts, trims | Your cutout per segment, for words behind your head |
| Rebuilds the script, picks the takes, places the cuts | Punch-ins, grade, text, captions, audio | Animated UI inserts (app on screen, profile follow) |
| Look, layout, caption copy, SFX choices | Preview frames and export | |
| QA of the exported frames and audio | Posting (by you, from the Edits window) | |

Each round of notes edits a plain `edl.json`, and Claude brings the Edits timeline in line with it. Unchanged parts are not touched, and cutouts are cached per segment.

---

## Requirements

- A Mac with Apple silicon (M1 or later): Edits desktop exists only there.
- [Instagram Edits for Mac](https://edits.instagram.com/desktop), signed in, with **Settings > Automation > Enable Automation Server** on.
- The [insta-edits bridge](https://github.com/faisalkhanzemi/insta-edits-for-claude) (independent, MIT). Without it Claude only ever sees Edits' home screen tools, never the editor.
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code), ffmpeg, Node.js 22+, Python 3.10+. `brew install ffmpeg node python`.
- Optional: an [Apify](https://apify.com) account to pull your own reels for the orbit and profile inserts.

Behind-head words need Edits to accept a video layer with transparency (or to cut you out itself). The skill tests that once on first run and falls back to putting the words beside your head if neither works.

---

## Install

1. In Edits: Settings > Automation > Enable Automation Server, copy the access token, keep Edits open.
2. In Claude Code:
   ```
   /plugin marketplace add faisalkhanzemi/insta-edits-for-claude
   /plugin install insta-edits@insta-edits
   ```
   Paste the token when asked (it goes to your keychain), then restart Claude Code. `/mcp` should list `edits`.
3. Install the skill:
   ```bash
   git clone https://github.com/erivaldodantas/video-edit-skill-instagram-edits "$HOME/.claude/skills/video-edit-insta-edits"
   ```
4. Run `/video-edit-insta-edits`. It installs under its own name, so it can live next to the original `/video-edit`. The first run asks your name, handle and favourite look, checks your tools, and probes what your Edits build can do (it works in a throwaway Edits project and deletes it afterwards).

Projects live under `~/Movies/reel-edits` by default: Edits is sandboxed and refuses to import from Downloads, Desktop or temp folders, so the skill copies your clips there. Your originals are never changed.

---

## Usage

```
/video-edit-insta-edits I just dropped 5 clips in my downloads
/video-edit-insta-edits use the cool girl look when I say "the cool girl aesthetic", bold everywhere else
the captions feel too small, and cut the pause before "or you can get"
```

Tips for filming: shoot vertical in 4K if you can (punch-ins stay sharp), lock the frame rate, keep the camera still for each setup, and repeat a line until it feels right.

---

## Known limits

- Songs from Edits' music library come out silent in exports started through automation. Add music from the Edits window, or use your own audio files.
- Claude never posts. You publish from Edits.
- Edits' automation server is undocumented and updates weekly; the skill re-probes it when the app version changes.
- Exact typography from the original skill is approximated with the text styles and fonts Edits offers.

---

## Credits

Original skill by [@tenfoldmarc](https://www.instagram.com/tenfoldmarc). Bridge by [faisalkhanzemi/insta-edits-for-claude](https://github.com/faisalkhanzemi/insta-edits-for-claude). Built on [HyperFrames](https://github.com/heygen-com/hyperframes) (background removal, inserts) and [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Fonts from Google Fonts (SIL OFL). Sound effects from Pixabay, downloaded on setup. Not affiliated with Meta or Instagram; "Instagram" and "Edits" are trademarks of Meta Platforms, Inc.
