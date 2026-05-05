# creative-designer

Generates on-brand Pinterest pins for Switzertemplates and submits approved pins to Tailwind.

---

## What it does

1. Takes a list of topics/keywords
2. Generates SEO-optimised copy for each pin (Claude) - headline, category label, SEO title, description
3. Generates a background photo for each pin (Gemini Imagen)
4. Composites text onto the photo with brand typography and overlay (Pillow)
5. Opens an HTML preview so you can review all pins visually
6. You mark which pins are approved
7. Approved pins are copied to `outputs/pins/approved/` and submitted to Tailwind as drafts

---

## Setup

```bash
cd skills/creative-designer
pip3 install -r requirements.txt
```

Fonts (Noto Serif Display Light + Montserrat) download automatically on first run.
They are cached in `skills/creative-designer/fonts/`.

API keys required in `.env` (project root):
- `ANTHROPIC_API_KEY` - for copy generation (Claude)
- `GOOGLE_API_KEY` - for background image generation (Gemini Imagen)
- `TAILWIND_API_KEY` - for Tailwind draft submission
- `TAILWIND_BOARD_ID` - (optional) Pinterest board ID for Tailwind drafts

---

## Usage

```bash
# Interactive - enter topics when prompted
python3 skills/creative-designer/main.py

# Inline topics
python3 skills/creative-designer/main.py --topics \
  "branding kit for coaches" \
  "premade wix website for small business" \
  "instagram templates for service providers"

# From a text file (one topic per line, # for comments)
python3 skills/creative-designer/main.py --topics-file topics.txt

# Skip Gemini image generation (uses warm gradient placeholder - good for copy testing)
python3 skills/creative-designer/main.py --topics "topic1" --skip-images

# Skip Tailwind submission (writes queue file only)
python3 skills/creative-designer/main.py --topics "topic1" --skip-tailwind
```

---

## Output structure

```
outputs/pins/
├── review/
│   └── YYYY-MM-DD-HHMMSS/
│       ├── 01_topic-slug/
│       │   ├── pin.png        1000x1500px final composite
│       │   └── meta.json      all copy + photo concept
│       ├── 02_topic-slug/ ...
│       └── review_summary.html  visual preview (opens in browser automatically)
└── approved/
    └── YYYY-MM-DD-HHMMSS/
        ├── 01_topic-slug/ ...
        └── tailwind_queue.json  approved pins ready for Tailwind
```

---

## Tailwind submission (Phase 1)

Tailwind requires a public image URL, not a local file path. For Phase 1:

- The queue file (`tailwind_queue.json`) contains all metadata ready to paste
- Upload the pin images to your hosting or directly in the Tailwind scheduler
- The Tailwind API call is implemented and will work automatically once `image_url` is set per pin

Phase 2 will add automated image hosting so the full API submission works end-to-end.

---

## Pin design spec

- Format: 1000x1500px, PNG, portrait
- Background: Gemini Imagen editorial-style photo, 2:3 ratio
- Overlay: dark warm semi-transparent layer (brand aesthetic)
- Headline: Noto Serif Display Light, white, lowercase, lower-left
- Category label: Montserrat Regular, all-caps, warm taupe, above headline
- Watermark: switzertemplates.com, bottom-right, subtle

Visual style is pulled from `context/visual-style-guide.md`.
Copy voice is pulled from `context/brand-voice.md`, `context/target-audience.md`, `context/product-catalog.md`.
