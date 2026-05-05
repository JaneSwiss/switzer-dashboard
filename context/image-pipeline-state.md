# image-pipeline-state.md — Pinterest Pin Image Pipeline State

This file documents the exact working state of the pin image generation pipeline
as of May 2026. Use it to restore or debug any component without guessing.

Files covered:
- `skills/creative-designer/image_generator.py` — Gemini + Pillow compositing
- `skills/pinterest-agent/copy_writer.py` — photo concept and headline generation

---

## 1. Gemini Prompt Structure

### How the prompt is built

```python
def _build_gemini_prompt(photo_concept: str, topic: str, variation_letter: str = "b") -> str:
    suffix = _MOOD_SUFFIXES.get(variation_letter.lower(), _MOOD_SUFFIXES["b"])
    return (
        "No text, no words, no letters, no numbers, no typography, "
        "no placeholder text, no lorem ipsum, no labels anywhere in the image. "
        f"{photo_concept}. "
        f"{suffix} "
        "Subject positioned in upper or right portion of frame. "
        "Lower-left area has generous negative space for text overlay. "
        "Aesthetic: quiet luxury, feminine, sophisticated, magazine quality. "
        "No text, no logos, no overlays in the image. "
        "Portrait orientation (2:3 ratio)."
    )
```

Structure of the assembled prompt string:

1. **No-text instruction** (always first): `"No text, no words, no letters, no numbers, no typography, no placeholder text, no lorem ipsum, no labels anywhere in the image. "`
2. **Photo concept brief** from `copy_data["photo_concept"]` (Claude-written, mood-specific scene)
3. **Mood suffix** — dynamic per variation letter (see below)
4. **Fixed composition tail**: subject upper/right, lower-left negative space, quiet luxury aesthetic, no text/logos, 2:3 portrait

### Mood suffixes per variation letter

**a — BRIGHT AIRY WHITE:**
```
Photography style: editorial, minimal, bright and airy. Lighting: bright natural daylight, crisp and clean. Saturation: muted, not vivid.
```

**b — WARM DARK MOODY:**
```
Photography style: editorial, minimal, warm and moody. Lighting: dramatic low warm light. Saturation: muted, rich.
```

**c — BEIGE NEUTRAL:**
```
Photography style: editorial, minimal, soft and neutral. Lighting: warm afternoon natural light, gentle. Saturation: muted, sandy tones.
```

**d — COOL GREY:**
```
Photography style: editorial, minimal, cool and polished. Lighting: overcast cool light, no warmth. Saturation: muted, desaturated.
```

**e — EARTHY BROWN:**
```
Photography style: editorial, minimal, warm and earthy. Lighting: amber warm lamp light. Saturation: muted, rich brown tones.
```

### Retry logic

- Max 3 attempts (`MAX_ATTEMPTS = 3`)
- On attempt 2 and 3, the retry prefix is prepended before the photo concept:
  `"CRITICAL: zero text, zero letters, zero numbers, zero words, zero typography anywhere in the image. Reject and regenerate if any text appears. "`
- Falls back to warm gradient placeholder if all 3 attempts fail

### Gemini model order

1. `imagen-4.0-generate-001`
2. `imagen-4.0-fast-generate-001`
3. `gemini-2.5-flash-image`
4. `gemini-3.1-flash-image-preview`
5. `gemini-3-pro-image-preview`

First successful response is used.

---

## 2. Pillow Compositing Logic

### Pin size

1000 × 1500px (2:3 portrait)

### Crop method

Cover-crop, top-left anchored — no stretching:

```python
scale = max(PIN_W / src_w, PIN_H / src_h)
new_w = int(src_w * scale)
new_h = int(src_h * scale)
bg    = bg.resize((new_w, new_h), Image.LANCZOS)
bg    = bg.crop((0, 0, PIN_W, PIN_H))
```

Crops from top-left (0, 0) so faces in upper portion are never cut.

### No overlay

**No dark overlay is applied to any pin.** The white headline box provides contrast.

### Pin styles by variation letter

All 5 variations (a–e) use the same base compositor: white headline box on photo.
The variation letter determines two things:

| Letter | CTA bar | Headline accent color |
|--------|---------|----------------------|
| a | No | Yes — cycling color (italic + color on highlight_words) |
| b | Yes — cycling bar color | No (dark italic only) |
| c | No | No (dark italic only) |
| d | No | Yes — cycling color (italic + color on highlight_words) |
| e | Yes — cycling bar color | No (dark italic only) |

### White headline box

```
Width:   86% of PIN_W = 860px
X pos:   centered horizontally = (1000 - 860) // 2 = 70px from edge
Padding: 48px horizontal, 40px vertical (inside box)
Text max width: 860 - 96 = 764px
Font: NotoSerifDisplay-Light, 64px
Line height: 64 + 18 = 82px
```

**Box vertical position (`_box_top_y`):**
- Variation `c` (overhead flat lay): top of box at `(1500 * 0.42) - (box_h // 2)` → center
- All other variations: top of box at `(1500 * 0.60) - (box_h // 2)` → lower portion
- Clamped to: `max(80, min(y, PIN_H - box_h - 80))`

### Headline text rendering

- All words rendered in `TEXT_DARK = (56, 56, 56)` by default
- `highlight_words` from copy_data drives accent selection (see section 4)
- Accented words: italic font + (for pins a and d) cycling accent color
- Non-accented words: regular font + dark charcoal

### Headline accent colors (pins a and d only)

Cycles by `(topic_id - 1) % 4`:

| Index | Color | Hex |
|-------|-------|-----|
| 0 | yellow | #F2C94C |
| 1 | pink | #E91E8C |
| 2 | blue | #4FC3F7 |
| 3 | terracotta | #C4714F |

### CTA bar (pins b and e only)

Appears directly below the white headline box (6px gap). Height auto-sizes to fit the CTA text in ≤2 lines. Font size auto-scales from 22–44px to fill the bar width.

CTA text: extracted from the last sentence of `seo_description` (after stripping hashtags).

CTA bar color cycles by `(topic_id - 1) % 5`:

| Index | Color | Hex |
|-------|-------|-----|
| 0 | black | #000000 |
| 1 | chocolate brown | #6B3F2A |
| 2 | warm terracotta | #C4714F |
| 3 | dusty sage | #7A8C6E |
| 4 | muted navy | #2C3E50 |

CTA text is always `TEXT_WHITE = (255, 255, 255)`.

### Watermark

`switzertemplates.com` — always centered at the bottom of the pin.
Font: Montserrat Regular (or Helvetica fallback), 18px.
Color: `LABEL_COLOR = (187, 176, 170)` warm taupe.
Position: `y = PIN_H - 42 = 1458px`

### Fonts

| Key | File | Use |
|-----|------|-----|
| `serif` | NotoSerifDisplay-Light.ttf | Headline regular |
| `serif_italic` | NotoSerifDisplay-LightItalic.ttf | Highlighted words |
| `sans` | Montserrat-Regular.ttf (falls back to Helvetica) | Watermark + CTA bar |

Both Noto Serif files download from Google Fonts on first run. Montserrat-Regular.ttf has a 404 issue on the current URL — system Helvetica is used as fallback.

---

## 3. Photo Concept Generation (`copy_writer.py`)

Claude generates the `design_brief` field for each variation. The instructions appear in two places: the output format schema and the user prompt rules.

### Mood assignment per variation letter

| Letter | Mood |
|--------|------|
| a | BRIGHT AIRY WHITE — pure white/cream, bright daylight, ultra-clean |
| b | WARM DARK MOODY — espresso browns, dramatic low light, dark warm shadows |
| c | BEIGE NEUTRAL — sandy beige/ivory, warm afternoon light, soft matte |
| d | COOL GREY — cool grey, overcast light, polished, no warmth |
| e | EARTHY BROWN — rich wood/brown tones, amber lamp light |

### Scene variety rules (non-negotiable)

The 5 briefs in a topic must be **visually distinct** — different subject, angle, props, and composition in every brief. Claude rotates through:

- Woman working at a desk
- Close-up of hands holding coffee or writing
- Overhead flat lay of a workspace
- Woman walking or standing outdoors in a professional setting
- Woman seated reading or thinking

**Never two similar compositions in the same topic.**

### Design brief format instruction (from output schema)

```
50+ words. Start with the MOOD keyword. Then write a specific, cinematic scene for
Gemini to generate. CRITICAL: the 5 briefs in a topic must be visually distinct —
different subject, angle, props and composition every time. Rotate through these
scene types: a woman working at a desk, a close-up of hands holding coffee or writing,
an overhead flat lay of a workspace, a woman walking or standing outdoors in a
professional setting, a woman seated reading or thinking. Always business-adjacent.
Never two similar compositions in the same topic. Never reference a screen or device
showing content. State the mood in the first line of the brief.
```

### User prompt rule (reinforces the above)

```
- design_brief: write 5 visually distinct scenes — different subject, angle, composition
  and setting in every brief. CRITICAL: never two similar scenes in the same topic.
  Rotate through: woman at a desk, close-up of hands/coffee/notebook, overhead flat lay,
  woman walking or standing in an outdoor or architectural setting, portrait of woman
  thinking or reading. Always business-adjacent. Never reference a screen showing content.
  Mood per variation (state in first line of brief):
  a=BRIGHT AIRY WHITE  b=WARM DARK MOODY  c=BEIGE NEUTRAL  d=COOL GREY  e=EARTHY BROWN
```

---

## 4. highlight_words Logic

### What it is

1-2 words from the `pin_headline` that carry the most emotional or commercial weight.
Chosen deliberately by Claude — the word(s) the audience will feel or act on.
Never a conjunction, preposition, article, or filler word. Always an array.

### How Claude is instructed to choose them

From the output schema:
```
1-2 words from the pin_headline that carry the most emotional or commercial weight.
Chosen deliberately — the word/s the audience will feel or act on. Never a conjunction,
preposition, article, or filler word.
Examples:
- 'Your website should win clients before you even speak to them' → ['win'] or ['win', 'clients']
- 'The gap between looking established and looking DIY' → ['established']
- 'Wix website template to look professional and attract more clients' → ['professional', 'clients']
Always an array even if only 1 word.
```

### How image_generator.py uses them

1. `_highlight_set(copy_data)` converts `highlight_words` to a lowercase set, stripping punctuation
2. `_is_accent(word, highlight, fallback_idx, fallback_set)` returns True if the word matches:
   - Primary: checks against `highlight_set` (if present)
   - Fallback: uses `_accent_word_indices()` which picks the last N non-stop-words algorithmically
3. Accented words get:
   - **Italic serif font** (for all pins)
   - **Cycling accent color** (pins a and d only — see accent color table above)
   - Non-accented words always use `TEXT_DARK = (56, 56, 56)` charcoal

---

## 5. Pipeline Entry Point

### For the Pinterest agent (full batch)

```bash
python3 skills/creative-designer/main.py \
  --from-topics-json data/pinterest-agent/topics-YYYY-MM-DD.json
```

The `--from-topics-json` flag maps Pinterest agent topic JSON fields to creative designer fields:
- `design_brief` → `photo_concept`
- `topic_id` → explicit topic number for color cycling
- `highlight_words` → passed through to accent rendering

### For single-topic testing

```python
cd = {
    "topic":           "wix website template (9a)",
    "topic_id":        9,            # explicit — drives accent + CTA bar color cycling
    "variation_id":    "9a",         # last char determines mood suffix and style
    "pin_headline":    "...",
    "highlight_words": ["professional", "clients"],
    "seo_description": "...CTA!",
    "photo_concept":   "BRIGHT AIRY WHITE. A woman ...",
    "destination_url": "https://...",
}
```

---

*Last updated: May 2026*
*Reflects the working state after the Pinterest Expert Agent — Creative Designer build sessions.*
