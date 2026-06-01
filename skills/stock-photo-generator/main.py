#!/usr/bin/env python3
"""
Stock Photo Generator — Switzertemplates
Generates dark-aesthetic business/success stock photos on demand.
Uses Claude to write the prompt, Gemini Imagen to generate the image.
All photos are 9:16 portrait (Pinterest / Instagram).

Run:
    python3 skills/stock-photo-generator/main.py "working late in dark office"
    python3 skills/stock-photo-generator/main.py --topics "jet lifestyle" "money mindset" "boss energy"
    python3 skills/stock-photo-generator/main.py                     (interactive mode)
"""

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types
from prompt_library import generate_batch, generate_single

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_BASE = ROOT / "outputs" / "stock-photos"

load_dotenv(ROOT / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GOOGLE_API_KEY    = os.getenv("NANO_BANANA_API_KEY")


# ── image prompt system ────────────────────────────────────────────────────────

PROMPT_SYSTEM = """You are generating image prompts for dark business lifestyle stock photos.

These images are for a female entrepreneur brand used on Pinterest and Instagram.
They must look like real photographs — not AI art, not studio renders, not plastic renders.
The overall aesthetic: dark, moody, sophisticated, aspirational. Every image must signal wealth and success.

---

PHOTOGRAPHY STYLE — these rules are what make photos look real. Follow every one exactly.

- Shot on iPhone 15 Pro Max. Not a professional camera. Not a photoshoot. A real person took this on their phone.
- iPhone night mode or low-light mode: characteristic digital grain and noise throughout, especially in shadows and dark areas. The grain is digital sensor noise — uneven, slightly coloured specks — not stylized film grain.
- Slightly soft focus — iPhone computational photography softens fine detail naturally. Skin has visible natural texture and pores, not smooth or retouched.
- Available light only — window light, indoor ambient, screen glow, car dashboard light. The lighting is uneven and imperfect, not balanced.
- Slight natural vignetting at the frame corners — darker edges, lighter centre, as a phone camera produces.
- Shallow depth of field from iPhone portrait mode — background is softly blurred with a slightly artificial bokeh edge that is characteristic of computational portrait mode.
- Intentionally imperfect: slightly off-centre framing, one element lightly cropped at the edge, uneven exposure, the scene is slightly tilted or casually framed.
- Candid energy throughout — person unaware of camera, scene genuine and unstaged, not composed for a shoot.
- No bright colours, no gradients, no studio lighting, no stock photography look, no digital sharpening, no professional retouching.
- LOW CONTRAST — lifted shadows, matte, slightly flat. iPhone photos in low light look soft and slightly underexposed, never punchy or high-contrast.
- Slightly underexposed. Dark but not pitch black — shadow detail is retained with grain visible in it.

COLOUR GRADING — strictly enforced:
- No orange. No warm tungsten glow. No golden-hour cast. No amber wash. Light is neutral white or the faintest warm, never orange.
- No blue. No cool blue tones. No blue shadows. No city-blue night cast. Shadows are dark grey-brown, never blue.
- No bright or saturated colours of any kind.
- Neutral, muted, desaturated overall — like a high-end lifestyle photo from 2025, not a colour-graded film.

---

COLOUR PALETTE — only these tones are allowed:
- Black and near-black (dominant throughout)
- Dark charcoal and dark grey
- Dark chocolate brown and espresso (bags, wood surfaces, leather)
- Gold — metallic accent only: jewellery, bag hardware, watch. Never a golden colour wash over the scene.
- Silver and cool grey (MacBook, stainless steel, mirror surfaces)
- Off-white and cream (coffee cups, cream car leather, paper — muted, never bright white)
- Dark forest green — only acceptable as a blazer or coat, never as background or surface
- NEVER: bright red, orange, bright blue, tan, burgundy, pink, or any saturated colour

---

WEALTH AND SUCCESS — every image must make this unmistakably clear:
If a woman is present: she is in a high-rise office, luxury car, private jet, penthouse, or upscale dark space.
If no person: the scene as a whole must communicate success through context — a dark workspace with a MacBook and designer bag in the frame together, a jet tray with a bag and headphones, a luxury car interior with a coffee cup in the cupholder. Never a single isolated object on a surface with no context. A bag on its own says "product photo". A bag on a jet seat beside AirPods says wealth.
Never generate a scene that could belong to an ordinary person's life.

---

WOMAN CHARACTER (when a person is present):
- Face: supermodel-level. Extremely high sharp cheekbones, strong defined jawline, full pouty lips, large striking eyes, perfectly arched thick brows, flawless warm golden skin. She looks like she belongs on the cover of Vogue — the kind of face that commands attention. NOT generic pretty. NOT girl-next-door. Striking, memorable, high-fashion.
- Hair: long, thick, and full of life. Voluminous bouncy waves, glossy blowout, or sleek straight with shine. Choose from:
  Rich dark brunette — long, wavy, voluminous, glossy, cascading
  Warm honey or platinum blonde — long, full-bodied waves or sleek straight
  Jet black — long, sleek with gloss or loose waves
- Makeup: full glam, warm-toned, never Gothic.
  Eyes: warm bronze or copper eyeshadow, golden shimmer on the lid, perfectly defined thick brows, long thick lashes. Eyeliner if it fits.
  Skin: glowing, dewy, sun-kissed bronze glow, golden highlighter on cheekbones and bridge of nose. Looks like the most beautiful version of a real person.
  Lips: warm nude, warm rosewood, caramel gloss. Full and defined. NOT dark, NOT plain.
- Expression: powerful, self-possessed, slightly cold. The look of someone who has already won. Not smiling. Engaged entirely in her own world.
- Outfit — always dark and expensive:
  Black blazer, black turtleneck, black leather jacket, tailored black coat, black cashmere
  Dark charcoal or very dark forest green blazer as rare alternative
- Accessories: structured black or dark chocolate Birkin or Kelly bag, bold chunky gold jewellery (stacked rings, thick cuff, layered chains, large hoops), gold Rolex or Cartier watch.
- Nails: long gel nails — warm nude, beige, or soft caramel. Never dark.
- Shoes when visible: black pointed stilettos.

---

VARIETY — two mandatory rules that must both be followed:

RULE 1 — SCENE TYPE: each image must be a different scene type. Never repeat within a batch:
TYPE A — female portrait, face fully visible, CLOSE CROP: face and shoulders fill the frame. Luxury environment background softly blurred behind.
TYPE B — female FULL BODY from behind, no face. Wide enough to show full outfit head to toe. Large luxury environment around her — she is not filling the whole frame.
TYPE C — female in luxury car. MEDIUM CROP: from waist up, steering wheel or window visible. She is clearly driving or seated.
TYPE D — EXTREME CLOSE-UP hands only. Tight crop — wrists and below only. No torso, no face. Dark background.
TYPE E — overhead flat lay. Camera directly above, looking straight down. Lifestyle objects on surface. No person.
TYPE F — dark desk scene. Camera at a 45-degree angle looking down at the desk. Not overhead, not eye-level. MacBook, objects, dark surface. No person.
TYPE G — jet or car interior WIDE SHOT. Show the full seat, tray table, porthole window, or car interior. Objects placed in scene. No person.
TYPE H — EXTREME CLOSE-UP of a single lifestyle detail: just the coffee cup in a cupholder, just the bag clasp, just the watch face, just the phone on a surface. Tight macro crop.
TYPE I — WIDE atmospheric night scene. Person or no person. City lights, dark room, candle, device. Scale is wide — the environment is the subject, not a face.
TYPE J — outdoor/architectural. WIDE or LOW ANGLE looking up. Buildings, street, jet exterior. No person. Dramatic scale.

RULE 2 — SCALE VARIETY: across any batch of 5+ images, the scales must be dramatically different from each other:
- At least one EXTREME CLOSE-UP (hands, object detail, face crop)
- At least one WIDE or FULL-BODY shot where a person is small in a large space
- At least one MEDIUM (waist up or desk scene)
- No two images at the same distance and angle

---

ENVIRONMENTS:

HIGH-RISE OFFICE (Types A, B, F):
- Floor-to-ceiling windows, misty or overcast city skyline visible, dark wood desk, black leather chairs, MacBook, overcast grey light from one side

LUXURY CAR (Types C, H):
- BMW, Mercedes-Benz, or Bentley. Interior: dark or charcoal leather seats, dark headliner, dark trim. Overcast light through windows, no orange interior lighting.

PRIVATE JET (Types A, B, I):
- Cream or off-white leather seats, dark wood trim, oval porthole showing grey sky or cloud, small tray table with props

PENTHOUSE OR HOTEL (Types A, B, I):
- Floor-to-ceiling dark glass windows, faint city lights outside, dark leather or dark marble surfaces, near-darkness

DARK DESK SETUP (Type F) — closely based on reference photos:
- Dark wood desk against a window, overcast grey light flooding in from one side
- MacBook open (screen blurred, no readable text), phone flat beside it, white ceramic mug, open planner or notebook, small desk lamp
- Very dark overall, low contrast, real and lived-in — like the reference photos of a real home office at dusk

FLAT LAY (Type E) — closely based on reference photos:
- Surface options: dark marble, dark leather desk pad, espresso-stained wood, or light grey boucle sofa fabric (as in the reference photos)
- Lighting: single directional window light from one side, soft diagonal shadows, never overhead flash
- Items loosely placed, slightly overlapping, casual not styled — like they were genuinely set down
- MUST include TECH: MacBook closed or partially open (silver), iPad Pro with keyboard case, or iPhone in a minimal black case
- MUST include a DRINK: latte with latte art in a matte ceramic cup, small espresso in a white cup, or iced coffee in a clear glass
- MUST include STATIONERY: leather-bound planner or thick notebook (dark or black cover), matte black or gold pen
- MUST include ACCESSORIES: gold jewellery casually placed — a chain laid loosely, 2–3 rings, a thin bracelet
- ADD 2–3 from this MIX: Diptyque or Jo Malone candle (white label on cream wax), YSL or Chanel beauty product (dark packaging), luxury serum or cream (minimal glass bottle), small black cosmetics pouch, AirPods Max (space grey or black), designer sunglasses (dark frame, folded), corner of a structured black bag
- No bright colours in any item — all products are black, dark, cream, or silver packaging

HANDS/CLOSE-UP (Type D):
- Manicured hands (nude or beige gel nails, gold rings, gold bangle or watch)
- Holding: takeaway coffee cup in black sleeve, luxury car steering wheel, iPhone, pen against a notebook, a folded $100 bill
- Background: dark and out of focus — car interior, dark desk, dark fabric

---

OUTPUT FORMAT — return ONLY the prompt text. No explanation. No label. Just the prompt itself.

The prompt must:
1. Open with the scene type, composition, and what is in the frame
2. Name the specific environment, surfaces, and light source
3. Describe the woman if present: hair type, makeup (warm/golden), outfit, accessories
4. State: shot on iPhone 15 Pro Max, iPhone night mode digital grain, slightly soft focus, portrait mode shallow depth of field, low contrast lifted shadows, available light only
5. End with this exact closing line:
   No text, no words, no labels, no readable typography anywhere in the image. No bright colours, no gradients, no studio lighting, no stock photography look, no digital sharpening, no professional retouching. Shot on iPhone 15 Pro Max, digital grain, low contrast, candid and unstaged. Portrait 9:16, high resolution.
"""


# ── core functions ─────────────────────────────────────────────────────────────

def generate_prompt(topic: str) -> str:
    """Call Claude to write a detailed Gemini Imagen prompt."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=700,
        system=PROMPT_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                f'Generate a dark business success stock photo prompt for this topic: "{topic}"\n'
                f"9:16 portrait. Signal wealth and success. "
                f"If a woman is present: supermodel-level face — extremely high cheekbones, sharp jaw, full lips, striking eyes, thick arched brows, golden glowing skin. Vogue cover material. Full glam warm makeup. Long voluminous hair. "
                f"Photography: shot on iPhone 15 Pro Max, iPhone night mode digital grain, slightly soft focus, portrait mode bokeh, low contrast lifted shadows, available light only. "
                f"Colour: neutral desaturated — no orange, no blue, no bright colours. Black, charcoal, dark chocolate, gold metallic accents only. "
                f"End with: No text, no words, no labels, no readable typography anywhere in the image. "
                f"No bright colours, no gradients, no studio lighting, no stock photography look, no digital sharpening, no professional retouching. "
                f"Shot on iPhone 15 Pro Max, digital grain, low contrast, candid and unstaged. Portrait 9:16, high resolution."
            ),
        }],
    )
    return response.content[0].text.strip()


def generate_image(prompt: str, output_path: Path) -> bool:
    """Call Gemini Imagen at 9:16 and save the result."""
    try:
        client = genai.Client(api_key=GOOGLE_API_KEY)
        response = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=prompt,
            config=genai_types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="9:16",
                output_mime_type="image/jpeg",
            ),
        )
        if response.generated_images:
            with open(output_path, "wb") as f:
                f.write(response.generated_images[0].image.image_bytes)
            return True
        print("  No image returned from Gemini.")
        return False
    except Exception as e:
        print(f"  Image generation failed: {e}")
        return False


def build_preview_html(results: list[dict], session_dir: Path) -> str:
    cards = ""
    for r in results:
        cards += f"""
  <div class="card">
    <div class="label">{r["topic"]}</div>
    <img src="{r["filename"]}" alt="">
  </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Stock Photos — {session_dir.name}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: #0d0d0d;
  font-family: Arial, sans-serif;
  padding: 3rem 2rem 5rem;
}}
h1 {{
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #333;
  margin-bottom: 0.4rem;
}}
.meta {{
  font-size: 11px;
  color: #252525;
  margin-bottom: 3rem;
}}
.grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 1.25rem;
}}
.label {{
  font-size: 10px;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: #333;
  margin-bottom: 0.5rem;
}}
img {{
  width: 100%;
  border-radius: 2px;
  display: block;
}}
</style>
</head>
<body>
<h1>Stock Photo Generator — Switzertemplates</h1>
<p class="meta">{session_dir.name} &nbsp;·&nbsp; 9:16 portrait &nbsp;·&nbsp; {len(results)} image(s)</p>
<div class="grid">
{cards}
</div>
</body>
</html>"""


# ── main ───────────────────────────────────────────────────────────────────────

def run():
    parser = argparse.ArgumentParser(
        description="Generate dark business success stock photos (9:16 portrait)"
    )
    parser.add_argument(
        "topic",
        nargs="?",
        help="Topic or scene description",
    )
    parser.add_argument(
        "--topics",
        nargs="+",
        metavar="TOPIC",
        help="One or more custom topics (quoted separately)",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=20,
        metavar="N",
        help="Number of photos to generate from the library (default: 20)",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Skip HTML preview — just save JPGs and open the folder",
    )
    args = parser.parse_args()

    # Build prompt list — library mode (default) or custom topics
    raw_prompts: list[str] = []
    topics: list[str] = []

    if args.topics:
        topics = args.topics
    elif args.topic:
        topics = [args.topic]
    else:
        # Library mode — generate N prompts from prompt_library.py
        n = args.batch
        print(f"Library mode — generating {n} prompts from scene library...")
        raw_prompts = generate_batch(n)
        topics = [f"scene_{i+1}" for i in range(len(raw_prompts))]

    if not topics:
        print("No topics entered. Exiting.")
        sys.exit(0)

    session_id = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    session_dir = OUTPUT_BASE / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nGenerating {len(topics)} image(s) — 9:16 portrait\nOutput → {session_dir}\n")

    results: list[dict] = []

    for i, topic in enumerate(topics, 1):
        print(f"[{i}/{len(topics)}] {topic}")

        try:
            if raw_prompts:
                prompt = raw_prompts[i - 1]
            else:
                prompt = generate_prompt(topic)
        except Exception as e:
            print(f"  Prompt generation failed: {e} — skipping.")
            continue

        slug = re.sub(r"[^\w]+", "-", topic.lower()).strip("-")[:60]
        filename = f"{slug}.jpg"
        out_path = session_dir / filename

        print("  Generating...")
        ok = generate_image(prompt, out_path)

        if ok:
            print(f"  Saved: {filename}")
            results.append({"topic": topic, "filename": filename, "prompt": prompt})
        else:
            print(f"  Failed — skipping.")

    if not results:
        print("\nNo images generated.")
        sys.exit(1)

    # Save all prompts to a text file in the session folder
    prompts_path = session_dir / "prompts.txt"
    prompts_text = ""
    for i, r in enumerate(results, 1):
        prompts_text += f"{'='*60}\nPHOTO {i} — {r['filename']}\n{'='*60}\n{r['prompt']}\n\n"
    prompts_path.write_text(prompts_text, encoding="utf-8")

    print(f"\n{'─' * 50}")
    print(f"Done. {len(results)}/{len(topics)} image(s) saved.")
    print(f"Folder  : {session_dir}")

    if not args.no_preview:
        preview_path = session_dir / "preview.html"
        preview_path.write_text(build_preview_html(results, session_dir), encoding="utf-8")
        print(f"Preview : {preview_path}")
        try:
            subprocess.run(["open", str(preview_path)], check=False)
        except Exception:
            pass
    else:
        try:
            subprocess.run(["open", str(session_dir)], check=False)
        except Exception:
            pass

    print(f"{'─' * 50}\n")


if __name__ == "__main__":
    run()
