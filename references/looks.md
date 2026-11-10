# Looks (design intent, applied in Edits)

These are the values the three looks were tuned to. In this edition Edits applies them: map each to the closest
control discovery found (grade sliders, LUTs, text styles, fonts, text animations) and judge the result on preview
frames, not on the numbers. CSS filter values below translate roughly as: contrast/saturation/brightness -> the
matching grade sliders (1.07 = +7%), sepia/warm soft-light -> warmth/temperature, hue-rotate -> tint, vignette ->
vignette. When Edits has no font from the list, use the closest it has in the same family (geometric sans, high-
contrast serif, wide-tracked caps) and keep the size ratios. Accent everywhere: butter yellow `#FAE67A`.

Effects that need a layer Edits cannot draw (words behind the head, the orbit's back copies) follow SKILL.md step 4.
The user's default look is in `config.json` (`defaultLook`); a line in the script that names a look
("you can get the cool girl aesthetic like this") switches that section to it.

## Bold (default base look)
Kinetic lowercase words placed around the speaker, the big ones tucked BEHIND the head.
- Grade on footage layers (`.g` = base video + cutout): `contrast(1.07) saturate(.9) brightness(.97)`, plus a soft-light teal/warm tone, light vignette, and dark gradients top/bottom for legibility. Keep skin natural: darker versions push faces red.
- Type: Inter Tight, lowercase, `letter-spacing:-.05em`, `line-height:.9`, white with soft shadow `0 10px 40px rgba(0,0,0,.55)`.
  - `sm` 84px/800 lead-in lines, `sm2` 56px/800 for long lines, `md` 150px, `big` 236px, `xl` 220px, `huge` 300px (900 weight). Yellow `y` class for the punch word.
- Layout: lead-in lines CENTRED in front of the speaker over the chest band (y ~950-1300). Lines pinned to the left edge look off.
- Big punch words BEHIND the head (`back` class sits below the cutout layer). Only the bottom ~25-30% of the letters may be covered (formula in layout.md); a fully hidden middle ("cla_de") reads as broken.
- Motion: each word blur-pops in on its spoken frame (`scale 1.22 + blur 22px -> 1`, .2s power3.out); groups blur out (.12s) and are hard-killed with `tl.set`.
- Every cut gets a punch (`#stage` scale 1.05 -> 1 over .32s).

## Cool girl
- Grade: `sepia(.18) saturate(.9) contrast(.93) brightness(1.05) hue-rotate(-5deg)` + warm soft-light overlay + soft warm vignette.
- Type: small calm lowercase Inter 500 (64px) + one punch line in **Instrument Serif italic** in butter yellow (200px in the top band, 150px for lower blocks so 3 words fit one line). Cream text `#FFF8EF`.
- Accents: yellow sparkles (✦) twinkling near the italic, optional handwritten note in Caveat 600 with a drawn SVG arrow (strokeDashoffset).
- No date/time stamps: they read as clutter.
- Signature move: the creator's own reels orbit them. In Edits: the reel tiles as overlay clips with position keyframes around an ellipse; the half of the ring behind the speaker needs `behind` placement and the speaker layer (SKILL.md step 4), otherwise keep the whole ring in front and beside the head. Original build: each reel tile exists twice (back copy below the cutout, front copy above), positions precomputed as GSAP keyframes every 0.1s around an ellipse, autoAlpha swapping at the ring's left/right extremes. Tiles 190x338, cream border. Keep the ring inside the safe zone.

## Cool dude (editorial studio look)
Inspired by high-end studio interview edits: dark room, lit subject, tiny tracked caps and big serif words.
- Grade: room `contrast(1.1) saturate(.84) brightness(.8) hue-rotate(-4deg)`, the speaker cutout lifted: `contrast(1.06) saturate(.86) brightness(.98)` so they stay lit while the room falls back. Teal soft-light tone + vignette (.5) + bottom gradient. Dark is good; NO film grain (it reads as noise on faces).
- Type: tiny wide-tracked caps in **Montserrat 500** (34px, letter-spacing .32em, words can be spread across the width with flex space-between) + heavy lowercase punch words in **DM Serif Display** (210-270px, italic for the final word). Cream `#F7F4EE`.
- Motion: serif letters rise from a mask (`yPercent 115 -> 0`, stagger .028, expo.out) with a blur/scale settle; tracked words "track in" via `scaleX 1.45 -> 1` + blur (NOT letterSpacing, lint rejects it); quick .45s blur-to-focus into the section; slow push-ins (scale 1 -> 1.05 across a shot) instead of cut punches; one soft light sweep (screen blend) when the section opens.
- Shots: wide, then a ~1.9x close-up cropped from the 4K original (alternate wide/close like a studio interview).
- Tried and dropped: replacing the room with an AI-generated background (looked fake), black and white, crushed-dark grades, film grain.

## Fonts on hand (assets/hyperframes/assets/fonts, used by generated inserts; Edits may not have them, latin woff2 + fonts.css, SIL Open Font License)
Inter 500/600, Inter Tight 800/900, Instrument Serif italic, DM Serif Display (+italic), Montserrat 500/600, JetBrains Mono 500, Caveat 600.
Add more with the Google Fonts CSS2 API + a Chrome user agent, keep only the `/* latin */` blocks, `font-display:block`.

## Avoid (they looked worse every time)
Orange captions, Anton / condensed poster caps, black and white grades, @handle watermarks in the corner, date stamps.
