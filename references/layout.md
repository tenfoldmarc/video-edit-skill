# Layout rules

Edits works in a normalised canvas (0..1, origin top-left, confirmed by discovery). The pixel values below are
for a 1080x1920 reel; divide x by 1080 and y by 1920 for Edits. Font sizes are kept in 1920-tall canvas pixels
(`size` in the EDL) and normalised as `S = size / 1920`.

## Instagram Reels safe zone (HARD)
| | px | normalised |
|---|---|---|
| Top clear (IG header) | 220 | y >= 0.115 |
| Bottom clear (username, caption, audio row) | nothing below 1470 | y <= 0.766 |
| Left/right | 35 | 0.033 |
| Right column (like/comment/share) from y 1155 down | 100 | x <= 0.907 when y >= 0.602 |

Check it, do not eyeball it: `qa_export.py --at <moments>` on the export, look at every still. Text boxes count with
their full extent (descenders, shadows), not just their anchor point.

## Where things go
- Lead-in caption lines: centred, chest band (y 0.49-0.68), in front of the speaker. Fine over the body, never over
  the face (eyes to chin).
- Punch words: behind the head near the top, or big over the chest.
- Cards/inserts: scale so the bottom edge ends at y <= 0.766. A card "under the face" starts below the chin (use
  `layers.json` `head.samples[].body` and the head-x span). A window "behind" the speaker is a `behind` insert whose
  bottom ~4% is overlapped by the head.
- Creator reel cards: 0.241 x 0.241 of the canvas (260x462 px), white border, slight tilt
  (-7 / +6 deg), beside the face, @handle under each (always credit them).

## Behind-head words (readability formula)
`matte.py` writes `head.canvas_head_top` per segment (the highest the head gets in that segment, already mapped
through the segment's zoom/cx/cy, 9:16 sources only). Let `H` be that value and `S = size / 1920`.
- Line height .9: baseline ~ top + 0.72*S, x-height ~ 0.5*S.
- Target: baseline = H + 0.3 * x-height = **H + 0.15*S**. The head then covers only the bottom ~25-30% of the letters.
- Convert the baseline to the anchor Edits uses for text (`coords.textAnchor` from discovery):
  top-left anchor -> `top = H + 0.15*S - 0.72*S`; centre anchor -> `y = H + 0.15*S - 0.72*S + 0.45*S`.
- Example: H = 0.208 (400 px), size 220 (S = 0.115): baseline 0.225, top 0.142 (~273 px).
- Smaller words (220) stay readable more easily than huge ones (300).
- Keep the whole word inside the safe zone; if the formula puts it above y 0.115, use a smaller size or put it in front.
- `head.moving` true (the head top moves more than 3% of the height in the segment): put the word in front over the
  chest instead. `head.warning` set (no subject, or not 9:16): place by preview frame and check it in QA.

## Cut timing
Segment start on the timeline = sum of the previous segments' durations, snapped by Edits to its frame grid. Read
the real cut times back from the timeline and pass them to `qa_export.py --cuts`; EDL arithmetic is only the
fallback.
