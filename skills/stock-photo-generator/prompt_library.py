"""
Prompt Library — Stock Photo Generator — Switzertemplates
All scenes are wide, zoomed-out, or environment-first.
NO medium shots or close-ups of people. NO face as the focus.
Women appear from behind, as silhouettes, full-body, or very small in a large environment.
"""

import random
import re as _re


# ══════════════════════════════════════════════════════════════════════════════
# VARIABLE POOLS
# ══════════════════════════════════════════════════════════════════════════════

HAIR = [
    "long voluminous deep brunette waves, glossy and full of movement",
    "long sleek platinum blonde hair, straight with a high-gloss finish",
    "long warm honey blonde waves, voluminous and full-bodied",
    "long jet black hair, sleek with a subtle shine",
    "long rich dark brown hair in a high sleek ponytail",
    "long dark hair in loose effortless waves",
    "long caramel-highlighted brunette waves with volume",
    "long straight deep chocolate brown hair",
]

WARM_MAKEUP = [
    "warm bronze and copper eyeshadow with gold shimmer on the lid, golden highlighter on cheekbones, warm rosewood lip",
    "soft warm brown shadow, dewy golden skin, warm caramel lip gloss",
    "golden shimmer on the lids, sun-kissed bronze glow, warm nude lip",
    "warm copper eye, glowing highlighted skin, soft mauve lip",
    "defined bronze eye, satin skin, warm beige lip with a gloss",
    "golden smoky eye kept soft, warm peach skin, nude glossy lip",
]

DRINK_COLD = [
    "a Starbucks iced latte in a clear cup with a green straw",
    "a Starbucks iced matcha latte in a clear cup with a green straw",
    "an iced coffee in a plain clear glass",
    "a latte in a ribbed clear glass",
    "a sparkling water in a dark glass bottle with a minimalist label",
    "a black Stanley tumbler in matte black",
    "a cold brew in a clear glass with ice",
]

DRINK_HOT = [
    "a small white ceramic espresso cup on a white saucer",
    "a white ceramic flat white",
    "a latte in a white ceramic cup with visible latte art",
    "a matcha in a handmade dark ceramic bowl",
    "an espresso in a small matte black ceramic cup on a black saucer",
    "a cappuccino in a wide white ceramic cup with foam",
]

DRINK_EVENING = [
    "a crystal wine glass with dark red wine",
    "a crystal champagne flute with pale gold bubbles",
    "a crystal wine glass with pale white wine",
    "a sparkling water in a crystal glass with ice",
]

DRINK_ANY = DRINK_COLD + DRINK_HOT

APPLE_DEVICE = [
    "a silver Apple MacBook Pro",
    "a space grey Apple MacBook Pro",
    "a silver Apple iPad Pro with a slim black keyboard case",
    "a space grey Apple iPad Pro with a slim keyboard folio",
    "a silver Apple MacBook Air",
]

PHONE = [
    "a silver Apple iPhone in a black leather case",
    "a black Apple iPhone in an all-black case",
    "an Apple iPhone in a dark Bottega Veneta style leather case",
]

BAG = [
    "a black Hermès Birkin 30 with gold hardware",
    "a dark chocolate Hermès Kelly 28 with gold hardware",
    "a black Hermès Kelly 25 with gold hardware",
    "a black structured Chanel classic flap bag",
    "a black Bottega Veneta Jodie bag",
    "a dark espresso brown Hermès Birkin with gold hardware",
    "a black Celine Box bag with gold hardware",
    "a black Saint Laurent Sac de Jour bag",
]

JEWELLERY = [
    "gold Cartier Love bangle and three stacked gold rings",
    "gold Rolex Datejust watch and two chunky gold rings",
    "layered gold chains, a thick gold cuff, and two gold rings",
    "large gold hoop earrings, a gold bangle, and three stacked gold rings",
    "Cartier Juste un Clou bracelet, a thin gold chain, and two rings",
    "bold gold drop earrings, a gold cuff, and stacked rings",
]

JEWELLERY_HANDS = [
    "three stacked gold rings on the right hand, a gold Cartier Love bangle on the left wrist",
    "two chunky gold rings, a gold Rolex Datejust visible on the wrist",
    "four stacked gold rings, a thick gold cuff on one wrist",
    "three gold rings including a thick signet, a gold Cartier Love bangle",
    "five stacked rings in mixed gold styles, a thin gold chain bracelet",
]

CANDLE = [
    "a lit Diptyque Baies candle in a white glass jar with a black oval label",
    "a lit Jo Malone London Peony & Blush Suede candle in a cream jar",
    "a small lit Diptyque Figuier candle",
    "a lit Maison Margiela Replica candle in a white apothecary jar",
    "a tall lit black candle in a minimal dark ceramic holder",
]

NOTEBOOK = [
    "a black Smythson Panama notebook",
    "a dark leather Hermès Ulysse agenda",
    "a thick dark Moleskine classic notebook",
    "a black Bottega Veneta leather notebook",
    "an open dark linen Appointed notebook",
    "a black Leuchtturm1917 hardcover notebook",
]

FLOWERS = [
    "a single white peony in a slim dark minimal bud vase",
    "three white tulips loosely placed at the edge of the frame",
    "a single white rose stem resting beside the notebook",
    "a loose arrangement of white ranunculus in a dark vase",
    "",
    "",
    "",
]

SURFACE_DARK = [
    "a black Calacatta marble surface with thin grey veining",
    "a dark espresso-stained oak wood surface with visible grain",
    "a matte black leather desk pad on a dark surface",
    "a very dark grey concrete surface with fine texture",
    "a deep charcoal slate surface",
    "a dark walnut wood surface with visible grain",
    "a black stone surface with subtle natural variation",
]

COAT_OUTFIT = [
    "a long structured black wool coat reaching her ankles",
    "a black oversized leather jacket over a black turtleneck",
    "a long dark charcoal cashmere coat",
    "a fitted black blazer over a black silk top",
    "a black leather trench coat",
    "a structured black double-breasted coat",
]

MONEY_PROP = [
    "a neatly banded stack of $100 bills",
    "a matte black luxury credit card",
    "a gold Rolex Submariner watch laid flat face up",
    "a Mercedes-AMG or Bentley key fob",
    "a gold Rolex Datejust watch",
    "a matte black Amex card and a gold card side by side",
]

SURFACE_PROP = [
    "a small matte black ceramic object beside the notebook",
    "a soft folded dark cashmere fabric draped at one edge of the frame",
    "a tortoiseshell claw clip resting casually near the corner",
    "a fine-line gold pen and a thin black pencil crossed beside the notebook",
    "a dark leather card holder placed at the corner",
    "",
]

BEAUTY_PRODUCT = [
    "a YSL Libre parfum bottle in dark glass and black metal",
    "a Chanel No.5 parfum bottle in dark glass with a black cap",
    "a Tom Ford Black Orchid parfum bottle",
    "a dark glass Byredo perfume bottle",
    "a minimal dark glass face serum bottle",
    "a matte black lip gloss tube",
]

SUNGLASSES = [
    "black Celine cat-eye sunglasses",
    "dark Prada rectangular sunglasses",
    "small black oval Gucci sunglasses",
    "black Saint Laurent rectangular sunglasses",
    "dark tortoiseshell Bottega Veneta sunglasses",
]

CLOSING = (
    "Shot on Kodak Portra 800 pushed, visible film grain throughout, {lens}mm lens, "
    "shallow depth of field, slightly soft focus, low contrast with lifted shadows. "
    "No text, no words, no writing, no labels, no readable typography anywhere in the image. "
    "No bright colours, no gradients, no studio lighting, no stock photography look, no digital sharpening. "
    "Portrait 9:16, high resolution."
)


# ══════════════════════════════════════════════════════════════════════════════
# SCENE TEMPLATES
# Rules: no medium shots of people, no faces as the focus, no close-ups of people.
# Women = full body, from behind, silhouette, or very small in a large space.
# ══════════════════════════════════════════════════════════════════════════════

SCENES = [

    # ── FLAT LAYS — 12 scenes, all different surfaces/angles/themes ──────────

    {
        "id": "flatlay_business_success",
        "lens": "35",
        "prompt": (
            "An overhead flat lay looking directly down at {surface_dark}. "
            "A business success arrangement, loosely placed and slightly overlapping: "
            "a silver Apple iPad Pro with a slim black keyboard case, "
            "{drink_hot}, "
            "{notebook} open with a gold pen, "
            "{money_prop}, "
            "{candle}, "
            "a gold chain bracelet and two chunky gold rings scattered naturally, "
            "{flowers}, {surface_prop}. "
            "Single directional window light casting long diagonal shadows. "
            "One edge of the iPad cropped at the top frame edge. "
        ),
    },
    {
        "id": "flatlay_morning_routine",
        "lens": "35",
        "prompt": (
            "An overhead flat lay looking directly down at {surface_dark}. "
            "A morning routine arrangement, items loosely placed: "
            "{apple_device} closed, "
            "{drink_hot}, "
            "{notebook} open with a gold pen, "
            "{beauty_product}, {beauty_product}, "
            "{candle}, "
            "gold jewellery scattered as if just removed — a chain, two rings, a bangle, "
            "{flowers}, {surface_prop}. "
            "Soft overcast window light from the left, long diagonal shadows. "
        ),
    },
    {
        "id": "flatlay_dark_money",
        "lens": "35",
        "prompt": (
            "An overhead flat lay looking directly down at {surface_dark}. "
            "A dark success flat lay — all props signal money and ambition: "
            "a neatly banded stack of $100 bills at the centre, "
            "{money_prop} beside the cash, "
            "{apple_device}, "
            "{drink_hot}, "
            "{phone} lying flat, screen dark, "
            "three chunky gold rings and a gold chain laid loose, "
            "{candle}. "
            "Single directional light, heavy shadows in the corners. "
        ),
    },
    {
        "id": "flatlay_travel_jet_tray",
        "lens": "50",
        "prompt": (
            "An overhead flat lay looking directly down at a dark walnut private jet tray table, "
            "cream leather seat surface and armrest partially visible at the edges. "
            "{apple_device} on the tray, "
            "{drink_cold} beside it, "
            "{notebook} with a gold pen, "
            "{phone} face-down, "
            "a gold chain bracelet casually placed, "
            "{beauty_product}. "
            "Overcast grey porthole window light from one side. "
        ),
    },
    {
        "id": "flatlay_sofa_lifestyle",
        "lens": "35",
        "prompt": (
            "A slightly elevated side-angle shot looking down at a cream bouclé sofa cushion surface — "
            "not directly overhead, camera at about 60 degrees, sofa back faintly visible behind the items. "
            "A closed silver Apple MacBook Pro with space grey Apple AirPods Max resting on top, "
            "{beauty_product} in dark packaging, "
            "{candle}, "
            "{phone}, "
            "{notebook}, "
            "{surface_prop}. "
            "Cream bouclé fabric texture visible around all items. "
            "Soft diffused indoor ambient light from the side. "
        ),
    },
    {
        "id": "flatlay_dark_beauty",
        "lens": "35",
        "prompt": (
            "A low side-angle shot at tabletop level, looking across {surface_dark} — "
            "camera is almost at surface height, objects loom large and background falls away. "
            "{beauty_product}, {beauty_product}, "
            "{sunglasses} placed face-down, "
            "{candle}, "
            "{flowers}, "
            "a gold chain necklace and two rings placed casually, "
            "{drink_hot}, "
            "{notebook} closed with a gold pen beside it. "
            "Directional window light, soft long shadows. "
        ),
    },
    {
        "id": "flatlay_dark_desk_angled",
        "lens": "35",
        "prompt": (
            "A 45-degree angled shot looking down at a dark desk surface. "
            "{apple_device} open with a softly blurred dark-mode screen. "
            "{drink_hot}. "
            "{money_prop} resting flat near the edge. "
            "{notebook} partially open, gold pen resting diagonally. "
            "{phone} face down. "
            "{candle} lit — only light source. "
            "Very dark scene, intimate and productive. "
        ),
    },
    {
        "id": "flatlay_hotel_bed",
        "lens": "35",
        "prompt": (
            "A 45-degree angled shot looking down at dark charcoal hotel bed linen — "
            "headboard and dark wall faintly visible behind. "
            "{apple_device} open and placed at an angle on the sheets, "
            "{bag} on the bed beside the device, "
            "{beauty_product}, "
            "{phone}, "
            "a gold chain and two rings scattered on the sheets, "
            "{notebook}. "
            "Very dim hotel room ambient light, device screen the main glow. "
        ),
    },
    {
        "id": "flatlay_car_seat",
        "lens": "50",
        "prompt": (
            "An angled shot looking down at the passenger seat of a black luxury car "
            "from the driver's perspective. "
            "{bag} sitting upright on the cream or dark leather seat, "
            "{drink_cold} in the cupholder just visible at the edge, "
            "{phone} lying flat on the seat beside the bag, "
            "{sunglasses} folded on the seat, "
            "dark leather seat texture and stitching visible. "
            "Overcast grey daylight from the car windows. "
        ),
    },
    {
        "id": "flatlay_dark_glass_table",
        "lens": "35",
        "prompt": (
            "A 45-degree angled shot looking down at a dark smoked glass table surface "
            "that faintly reflects the items — camera angle shows both the surface and "
            "the blurred dark room behind. "
            "{apple_device} open, reflection visible in the glass below, "
            "{drink_evening} beside it, "
            "{candle} flame reflected in the glass surface, "
            "{notebook} closed with {money_prop} on top, "
            "a loose gold chain and ring caught in the reflection. "
            "Only candle and device screen provide light. "
        ),
    },
    {
        "id": "flatlay_airport_lounge",
        "lens": "50",
        "prompt": (
            "A 45-degree angled shot looking down at a dark stone airport lounge table. "
            "{apple_device} open beside a dark leather seat armrest partially in frame, "
            "{drink_cold} on the table, "
            "{bag} partially visible at the bottom of frame, "
            "{notebook} open with a gold pen, "
            "{phone} face down, "
            "{sunglasses} resting near the edge. "
            "Dim muted airport lounge light. Scene feels exclusive and transient. "
        ),
    },
    {
        "id": "flatlay_concrete_editorial",
        "lens": "35",
        "prompt": (
            "An overhead flat lay looking directly down at a very dark grey concrete surface. "
            "A minimal editorial arrangement: "
            "{apple_device} closed, "
            "{money_prop} placed at a diagonal, "
            "{drink_hot} in a dark ceramic cup, "
            "{sunglasses} folded beside the cup, "
            "a single chunky gold ring and a thin bangle placed separately, "
            "{flowers}. "
            "Hard directional side light creating sharp deep shadows. Very minimal. "
        ),
    },

    # ── CAR SCENES — 4 truly distinct compositions ────────────────────────────

    {
        "id": "car_stepping_out_mercedes",
        "lens": "35",
        "prompt": (
            "A full-body wide editorial shot — woman stepping out of a black Mercedes-Benz S-Class "
            "on a dark city street. Full body visible head to below knee. "
            "She wears {coat_outfit}, black pointed stilettos on dark wet pavement. "
            "{bag} held at her side. {jewellery}. {hair} visible from the front but camera is wide. "
            "Dark glass shopfronts and muted city architecture behind her, overcast grey light. "
            "She looks ahead, mid-stride, unaware of camera. "
            "Car door open beside her, cream interior visible. "
        ),
    },
    {
        "id": "car_gwagon_arrival",
        "lens": "35",
        "prompt": (
            "A full-body wide shot from behind a beautiful woman opening the door "
            "of a matte black Mercedes-AMG G-Wagon. "
            "{hair} visible from behind. She wears {coat_outfit}, black trousers. "
            "One hand grips the heavy G-Wagon door handle, "
            "the other holds {bag}. "
            "Dark building facade behind, overcast flat daylight. "
            "Massive matte black G-Wagon body fills the left side of the frame, large AMG wheels visible. "
        ),
    },
    {
        "id": "car_cupholder_detail",
        "lens": "50",
        "prompt": (
            "A close-up angled shot looking down at a luxury car centre console — no person. "
            "{drink_cold} in the black leather cupholder. "
            "{phone} lying flat on the console beside it. "
            "Black stitched leather surfaces, gear shifter and dark controls visible. "
            "Overcast grey light from the windscreen. No orange lighting. "
        ),
    },
    {
        "id": "luxury_car_parked_night",
        "lens": "35",
        "prompt": (
            "A wide exterior shot of a black Bentley Continental or Rolls-Royce Ghost "
            "parked on a dark rain-slicked street in a luxury city district at night — no person. "
            "The car occupies most of the frame. "
            "Dark glass shopfronts and stone buildings line the street behind. "
            "Streetlights reflect off the wet black pavement and the car's polished bodywork. "
            "The scene is dark, moody, and expensive. "
            "Overcast night sky above, no bright lights in the scene. "
        ),
    },

    # ── OFFICE AND WORK SCENES — 5 distinct compositions ─────────────────────

    {
        "id": "office_window_active",
        "lens": "35",
        "prompt": (
            "A wide dark editorial scene — woman from behind, full body, "
            "standing at floor-to-ceiling windows in a high-rise corner office, "
            "small in the large dramatic space. "
            "She wears {coat_outfit}, black pointed stilettos. {hair} cascades down her back. "
            "She holds {drink_cold} in one hand mid-sip and {phone} in the other — active, not static. "
            "Dark walnut desk behind her holds {bag} and {apple_device}. "
            "Grey overcast city skyline through rain-speckled glass. "
        ),
    },
    {
        "id": "desk_from_behind_louboutin",
        "lens": "50",
        "prompt": (
            "A medium-wide editorial shot from behind a woman seated at a dark walnut desk, "
            "angled slightly to show her profile — no face visible. "
            "{hair} cascades down her back. She wears a fitted black blazer dress. "
            "Louboutin black stilettos with a red sole visible beneath the desk. "
            "{bag} upright on the desk to her right. "
            "{apple_device} open in front of her — she is typing, mid-task. "
            "{drink_hot} to one side, {notebook} open with a gold pen. "
            "Warm ambient light from behind, soft and diffused. "
        ),
    },
    {
        "id": "office_desk_night_candle",
        "lens": "35",
        "prompt": (
            "A 45-degree angled shot looking down at a dark wood desk at night — "
            "wide enough to show the full desk surface and the dark room around it. "
            "A beautiful woman's forearms and hands barely visible at the edge of frame, "
            "typing on {apple_device}. "
            "{drink_evening} to the side. "
            "{candle} — the only warm light source, its reflection on the dark desk surface. "
            "City lights blurred through a window in the background. "
            "{notebook} partially open, gold pen resting on it. "
        ),
    },
    {
        "id": "office_wide_empty",
        "lens": "35",
        "prompt": (
            "A wide atmospheric shot of a luxury high-rise office interior — no person. "
            "Floor-to-ceiling windows span the full width, grey misty city skyline outside. "
            "A dark walnut executive desk in the foreground: "
            "{apple_device} open with a blurred dark screen, "
            "{drink_hot} beside it, "
            "{notebook} open with a gold pen, "
            "{bag} on the desk as if just set down. "
            "Black leather executive chairs, dark hardwood floor. "
            "Overcast flat light from windows, deep shadows in the room behind. "
        ),
    },
    {
        "id": "executive_office_wide_empty",
        "lens": "35",
        "prompt": (
            "A wide atmospheric shot of a dark luxury executive office — no person. "
            "Dark charcoal walls, dark hardwood floor. "
            "Floor-to-ceiling window on the right showing a city skyline — "
            "towers and sky visible outside. "
            "A dark executive desk: {apple_device} open with a blurred screen, "
            "{notebook} closed with a pen beside it. "
            "A large black leather executive chair behind the desk, slightly turned. "
            "A large abstract artwork in dark tones on the wall to the left. "
            "The contrast between dark interior and city light through the window "
            "creates dramatic natural lighting. "
        ),
    },

    # ── PRIVATE JET SCENES — 4 distinct compositions ─────────────────────────

    {
        "id": "jet_tray_no_person",
        "lens": "50",
        "prompt": (
            "A close editorial shot of a private jet tray table and seat area — no person. "
            "{bag} standing upright on the cream leather seat beside the tray. "
            "Space grey Apple AirPods Max on the dark walnut tray table. "
            "{drink_cold} in the cup holder. "
            "{notebook} closed on the tray surface. "
            "Oval porthole window in the background shows soft grey overcast sky. "
            "Cream leather seat texture, dark wood trim. "
        ),
    },
    {
        "id": "jet_seat_wide",
        "lens": "35",
        "prompt": (
            "A wide editorial shot showing two private jet seats and the aisle between them. "
            "A beautiful woman is seated in the left seat — visible from head to knee, full body. "
            "{hair}. She wears {coat_outfit}. "
            "{bag} on the empty seat beside her. "
            "{drink_cold} on the tray table in front of her. "
            "She looks out the porthole window, absorbed in thought. "
            "Cream leather seats, dark walnut panelling, oval porthole windows showing grey sky. "
            "The full luxury of the jet interior is the subject — she is part of the scene. "
        ),
    },
    {
        "id": "jet_wide_interior",
        "lens": "35",
        "prompt": (
            "A wide editorial shot showing the full private jet cabin interior — "
            "a beautiful woman is small in the frame, seated in a cream leather chair "
            "toward the back of the cabin. "
            "Multiple oval porthole windows line the fuselage, grey sky beyond each. "
            "{hair}. She wears {coat_outfit}. "
            "{bag} visible on the seat beside her. "
            "{drink_cold} on the tray table in front of her. "
            "Dark walnut finishes, cream leather throughout. "
            "The cabin architecture is the subject — she is elegantly placed within it. "
        ),
    },
    {
        "id": "jet_from_aisle_wide",
        "lens": "35",
        "prompt": (
            "A wide editorial shot looking down the aisle of a private jet cabin "
            "from the front toward the rear. "
            "A beautiful woman is seated halfway down, small in the frame. "
            "{hair} visible. She wears {coat_outfit}. "
            "{bag} on the seat beside her. "
            "Multiple oval porthole windows on both sides, soft grey cloud light through each. "
            "Dark walnut panelling, cream leather seats, polished floor. "
            "The jet's interior architecture fills the frame — she is elegantly placed within it. "
        ),
    },

    # ── ARRIVAL AND STREET SCENES — 4 distinct compositions ──────────────────

    {
        "id": "street_luxury_hotel_arrival",
        "lens": "35",
        "prompt": (
            "A full-body wide editorial shot outside a dark luxury hotel entrance at dusk. "
            "A beautiful woman arrives — full body visible head to toe, "
            "stepping toward the entrance from a black luxury car parked behind her. "
            "{hair}. She wears {coat_outfit}, black pointed stilettos. "
            "{bag} in one hand. {jewellery}. "
            "Dark stone hotel facade, brass fittings, dramatic evening shadow. "
            "Scene feels like an arrival — she owns the space. "
        ),
    },
    {
        "id": "elevator_full_body",
        "lens": "35",
        "prompt": (
            "A full-body editorial shot of a beautiful woman "
            "standing in a large brushed steel elevator — full height of the frame, "
            "shot from slightly below eye level. "
            "She faces slightly away from camera — three-quarter from behind. "
            "{hair} down her back. She wears {coat_outfit}, black pointed stilettos. "
            "{bag} on one shoulder. {apple_device} tucked under her arm. "
            "Brushed stainless steel elevator walls floor to ceiling behind her. "
            "Her whole body is in frame — the environment visible around her. "
        ),
    },
    {
        "id": "penthouse_view_down_city",
        "lens": "35",
        "prompt": (
            "A wide atmospheric shot from inside a dark luxury penthouse, "
            "looking outward through floor-to-ceiling glass at the city far below at night. "
            "A dark marble side table just in frame holds {drink_evening} and {candle}. "
            "{bag} on a dark leather chair at the edge of the frame. "
            "A beautiful woman stands at the glass, back to camera — full body visible, "
            "{hair} cascading down. She wears {coat_outfit}. "
            "She looks down at the city — scale makes her feel powerful. "
            "Room behind her in complete darkness. "
        ),
    },

    # ── NIGHT AND ATMOSPHERIC — 7 distinct compositions ──────────────────────

    {
        "id": "penthouse_night_laptop",
        "lens": "35",
        "prompt": (
            "A dark penthouse table scene at night, camera at a 45-degree angle looking down. "
            "Black marble table occupies the lower two-thirds of the frame. "
            "{apple_device} open, screen casting a cool grey glow. "
            "{drink_evening} beside it. "
            "{candle} — flame the only warm point of light, reflected in the marble. "
            "{money_prop} placed casually, {notebook} beside it. "
            "Floor-to-ceiling glass fills the upper third — "
            "pitch-black night, distant city reduced to tiny soft white light points. "
            "Room completely dark. "
        ),
    },
    {
        "id": "dark_cafe_working",
        "lens": "35",
        "prompt": (
            "A dark editorial café scene at a private corner table — no person. "
            "{apple_device} open on a near-black table, screen blurred. "
            "{drink_hot} beside it. "
            "{notebook} with a gold pen on top. "
            "{sunglasses} on the table. "
            "Dark interior behind — dim overhead spot lights, rest in deep shadow. "
            "Dark wood or black marble table with real texture. "
        ),
    },
    {
        "id": "hotel_room_dark",
        "lens": "35",
        "prompt": (
            "A wide dark hotel room scene at night — no person. "
            "Dark marble desk by the window: "
            "{apple_device} open with a blurred dark screen, "
            "{drink_evening} beside it, "
            "{candle} lit. "
            "Floor-to-ceiling curtains half drawn, city lights softly visible through the gap. "
            "{bag} placed on the dark bed in the background, partially visible. "
            "Room almost entirely dark — only candle and screen provide light. "
        ),
    },
    {
        "id": "penthouse_window_silhouette",
        "lens": "35",
        "prompt": (
            "A wide atmospheric shot inside a dark penthouse at night. "
            "A beautiful woman stands at a floor-to-ceiling window — "
            "backlit by city lights, creating a full silhouette. Full body visible. "
            "{hair} visible as a dark outline. She wears {coat_outfit}. "
            "{bag} held at her side. "
            "She holds {drink_cold} in her free hand, looking out. "
            "City is a soft blur of light points below and behind her. "
            "Room interior in complete darkness. "
        ),
    },
    {
        "id": "dark_work_late",
        "lens": "35",
        "prompt": (
            "A wide atmospheric shot of a woman working late at a dark desk — "
            "room, desk, and woman all visible. She is seen from behind or three-quarter, "
            "not a close-up. {hair}. She wears a black cashmere top or black silk shirt. "
            "She leans slightly forward at {apple_device} — laptop open, screen blurred. "
            "{drink_evening} on the desk. {candle} lit — only light source. "
            "Dark room surrounds her. City window in the background shows distant dark city. "
            "The whole scene: late night, ambitious, wealthy, alone. "
        ),
    },

    # ── WIDE ENVIRONMENTAL — woman small in large space ──────────────────────

    {
        "id": "penthouse_wide_woman_sofa",
        "lens": "35",
        "prompt": (
            "A wide atmospheric shot inside a dark luxury penthouse at night — "
            "environment is the subject, woman is part of the scene. "
            "A beautiful woman seated on a dark leather sofa at the left of frame, "
            "{hair} visible, she wears {coat_outfit} — seen from the side or three-quarter behind. "
            "{bag} placed on the sofa beside her. "
            "{drink_evening} on a dark marble side table in front of her. "
            "Floor-to-ceiling glass windows dominate the right half — "
            "city lights soft and blurred outside at night. "
            "The room is vast and dark, only the city glow providing light. "
        ),
    },
    {
        "id": "dark_cafe_woman_wide",
        "lens": "35",
        "prompt": (
            "A wide dark editorial café scene — a beautiful woman seated at a dark corner table "
            "is a medium-small element in the frame, the moody café environment surrounding her. "
            "{hair}. She wears {coat_outfit}. "
            "{bag} on the chair or table beside her. "
            "{apple_device} open on the table — she looks at the screen. "
            "{drink_hot} beside the laptop. "
            "Dark café interior fills the frame: dark wood tables, dim spot lighting, "
            "other tables in deep shadow behind. "
        ),
    },
    {
        "id": "office_over_shoulder",
        "lens": "50",
        "prompt": (
            "An over-shoulder editorial shot — camera positioned behind and above "
            "a beautiful woman's right shoulder, showing her back and the desk ahead of her. "
            "{hair}. She wears {coat_outfit}. "
            "{apple_device} open on a dark desk ahead, screen blurred. "
            "{drink_hot} beside the laptop. "
            "{bag} visible at the edge of the desk. "
            "City window visible beyond the laptop, overcast grey light. "
            "{jewellery_hands} resting near the keyboard, mid-pause. "
        ),
    },
    {
        "id": "woman_with_bag_city",
        "lens": "35",
        "prompt": (
            "A full-body wide editorial shot from behind — a beautiful woman "
            "walking on a dark city street, full body head to heel in frame. "
            "{hair} down her back. She wears {coat_outfit}, black stilettos. "
            "{bag} carried on one arm. {jewellery} visible. "
            "Dark blurred city shopfronts and architecture behind her, overcast grey daylight. "
            "Mid-stride, purposeful, unaware of camera. "
        ),
    },

    # ── NEW REFERENCE-BASED SCENES ────────────────────────────────────────────

    {
        "id": "outdoor_cafe_table_elevated",
        "lens": "35",
        "prompt": (
            "A 45-degree elevated shot looking down at a small round dark bistro table "
            "on an outdoor terrace or cobblestone street. "
            "On it: a crystal wine glass with dark red wine, "
            "{drink_hot}, "
            "an open magazine or large-format book lying flat, "
            "{phone} resting on the magazine, "
            "{flowers}. "
            "A dark bistro chair visible at the top of the frame, empty. "
            "Cobblestone pavement or dark stone terrace visible in the background. "
            "Light purple or white flowering plants in a planter softly blurred behind. "
            "Natural overcast daylight, soft shadows across the table. No person visible. "
        ),
    },
    {
        "id": "tech_on_dark_fabric",
        "lens": "50",
        "prompt": (
            "A 45-degree angled shot looking down at items resting on a crumpled dark cashmere "
            "or wool fabric — a dark grey or dark olive coat or blanket thrown casually, "
            "creating texture and folds across the entire frame. "
            "{apple_device} open, screen dark or blurred. "
            "Space grey Apple AirPods Max headphones resting beside it. "
            "{drink_cold} nestled beside the laptop in the fabric folds. "
            "{surface_prop}. "
            "No surface visible — only the dark fabric and items on top. "
            "Very dim indoor ambient light, dark grey-charcoal tones throughout. "
        ),
    },
    {
        "id": "overhead_cafe_two_devices",
        "lens": "35",
        "prompt": (
            "A true overhead shot looking directly down at a round dark café table — "
            "the full circle fills the frame. "
            "A silver Apple MacBook Pro open at the bottom of the frame, "
            "a silver Apple iPad Pro with slim keyboard case in the centre, screen blurred. "
            "Space grey Apple AirPods Max between the devices. "
            "{drink_cold} at the top left, a second iced drink at the top right. "
            "A hand with {jewellery_hands} barely visible at the bottom edge — "
            "only fingers, no face or body. "
            "Dark table surface. Items placed as if mid-work session. "
        ),
    },
    {
        "id": "hands_marble_macbook",
        "lens": "50",
        "prompt": (
            "A 45-degree angled shot from the side looking down at a black marble surface "
            "with dramatic white veining. "
            "A space grey Apple MacBook Pro open in the right portion of the frame. "
            "A woman's two hands rest on the laptop — long white or light nude gel nails, "
            "five to six stacked rings across both hands: "
            "chunky gold signet, thin gold bands, a diamond-set band. "
            "A white takeaway coffee cup placed on the marble to the left. "
            "Black sleeve or coat cuff visible at the wrists. "
            "Deep black marble surface fills most of the frame. "
            "Faint ambient interior light only. No face, no upper body visible. "
        ),
    },
    {
        "id": "woman_desk_focused_candle",
        "lens": "35",
        "prompt": (
            "A medium-wide editorial shot from behind a beautiful woman working at a dark desk, "
            "seen from three-quarter behind — no face visible. "
            "{hair} in a loose bun or falling over one shoulder. "
            "She wears a dark blazer or black cashmere top. "
            "She writes in {notebook}, open to a page of notes, with a gold pen — head bowed in focus. "
            "{apple_device} open beside the notebook, screen blurred. "
            "{candle} at the back of the desk, casting the only warm light. "
            "{drink_hot} beside the laptop. "
            "{flowers}. "
            "Dark desk, dark room — candle and screen are the only light. "
        ),
    },
    # ── WIDE FEMALE SCENES WITH FACES — full body or wide environment ─────────

    {
        "id": "car_driving_wide",
        "lens": "35",
        "prompt": (
            "A wide editorial shot from the passenger seat of a black Mercedes-Benz S-Class — "
            "the full driver's area visible: woman, steering wheel, dashboard, windscreen, and interior. "
            "A strikingly beautiful woman drives — supermodel features, sharp cheekbones, full lips, "
            "warm glowing skin. {hair}. {warm_makeup}. "
            "She wears a black leather jacket or black blazer. "
            "Both hands on the steering wheel, {jewellery_hands} visible. "
            "{drink_cold} in the centre console cupholder — clearly in frame. "
            "Black leather seats, dark headliner above, gear console visible. "
            "Wet grey city pavement and overcast sky through the windscreen. "
            "Her gaze on the road, unaware of the camera. "
        ),
    },
    {
        "id": "jet_woman_wide_seat",
        "lens": "35",
        "prompt": (
            "A wide editorial shot inside a private jet — "
            "a strikingly beautiful woman seated in a cream leather chair, "
            "full body visible from head to feet, the jet interior surrounding her. "
            "Supermodel features, {hair}, {warm_makeup}. "
            "She wears {coat_outfit}. {jewellery}. "
            "{bag} on the seat beside her. {drink_cold} on the tray table. "
            "She looks out the porthole window beside her. "
            "Multiple cream leather seats, dark walnut trim, oval porthole windows visible. "
            "Flat grey cloud light through the portholes. "
            "The full luxury of the jet interior is the subject — she belongs in this world. "
        ),
    },
    {
        "id": "woman_penthouse_night_wide",
        "lens": "35",
        "prompt": (
            "A wide atmospheric shot inside a dark luxury penthouse at night. "
            "A strikingly beautiful woman seated at a dark glass or marble table, "
            "full body in frame — the room and city window dominate, she is part of the scene. "
            "Supermodel features. {hair}. {warm_makeup}. "
            "She wears a black silk outfit or dark cashmere. {jewellery}. "
            "{drink_evening} in front of her, {candle} lit on the table. "
            "Floor-to-ceiling windows behind her — city lights soft and blurred at night. "
            "She looks toward the window or at her phone, self-contained and powerful. "
        ),
    },
    {
        "id": "woman_hotel_lobby_wide",
        "lens": "35",
        "prompt": (
            "A wide editorial shot inside a dark luxury hotel lobby or corridor — "
            "a strikingly beautiful woman walks through the space, full body visible, "
            "the grand architecture surrounding her. "
            "She is confidently mid-stride but not the only subject — "
            "the opulent space is equally important. "
            "Supermodel features. {hair}. {warm_makeup}. "
            "She wears {coat_outfit}, black stilettos. {bag} on her arm. "
            "Dark marble floors, gold fittings, dark walls with architectural lighting. "
            "The lobby is large, she is elegant within it. "
        ),
    },


]


# ══════════════════════════════════════════════════════════════════════════════
# GENERATION FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def _fill(template: str) -> str:
    pools = {
        "hair":             HAIR,
        "warm_makeup":      WARM_MAKEUP,
        "drink_cold":       DRINK_COLD,
        "drink_hot":        DRINK_HOT,
        "drink_evening":    DRINK_EVENING,
        "drink_any":        DRINK_ANY,
        "apple_device":     APPLE_DEVICE,
        "phone":            PHONE,
        "bag":              BAG,
        "jewellery":        JEWELLERY,
        "jewellery_hands":  JEWELLERY_HANDS,
        "candle":           CANDLE,
        "notebook":         NOTEBOOK,
        "flowers":          FLOWERS,
        "surface_dark":     SURFACE_DARK,
        "coat_outfit":      COAT_OUTFIT,
        "money_prop":       MONEY_PROP,
        "surface_prop":     SURFACE_PROP,
        "beauty_product":   BEAUTY_PRODUCT,
        "sunglasses":       SUNGLASSES,
    }
    for key, pool in pools.items():
        placeholder = "{" + key + "}"
        while placeholder in template:
            template = template.replace(placeholder, random.choice(pool), 1)

    template = _re.sub(r',\s*,', ',', template)
    template = _re.sub(r',\s*\.', '.', template)
    template = _re.sub(r'\s{2,}', ' ', template)
    return template.strip()


def generate_batch(n: int = 20) -> list:
    scenes = SCENES.copy()
    random.shuffle(scenes)
    prompts = []
    for i in range(n):
        scene = scenes[i % len(scenes)]
        body = _fill(scene["prompt"])
        closing = CLOSING.format(lens=scene["lens"])
        prompts.append(body + " " + closing)
    return prompts


def generate_single(scene_id=None) -> str:
    if scene_id:
        scene = next((s for s in SCENES if s["id"] == scene_id), None)
        if not scene:
            raise ValueError(f"Scene '{scene_id}' not found.")
    else:
        scene = random.choice(SCENES)
    body = _fill(scene["prompt"])
    closing = CLOSING.format(lens=scene["lens"])
    return body + " " + closing


def list_scenes() -> list:
    return [s["id"] for s in SCENES]


if __name__ == "__main__":
    print(f"Library: {len(SCENES)} scenes\n")
    for p in generate_batch(5):
        print(f"\n{'─'*60}")
        print(p)
