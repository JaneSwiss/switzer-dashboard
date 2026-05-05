from __future__ import annotations

import os
import time
import hashlib
import requests
from pathlib import Path


def _signature(params: dict, api_secret: str) -> str:
    """Build a Cloudinary signed-upload signature (SHA-1 of sorted params + secret)."""
    body = "&".join(f"{k}={v}" for k, v in sorted(params.items())) + api_secret
    return hashlib.sha1(body.encode()).hexdigest()


def upload_pin(image_path: Path, slug: str) -> str:
    """
    Upload a pin PNG to Cloudinary under switzertemplates/pins/.
    Returns the public HTTPS URL.

    Requires in .env:
      CLOUDINARY_CLOUD_NAME
      CLOUDINARY_API_KEY
      CLOUDINARY_API_SECRET
    """
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    api_key    = os.getenv("CLOUDINARY_API_KEY", "")
    api_secret = os.getenv("CLOUDINARY_API_SECRET", "")

    if not all([cloud_name, api_key, api_secret]):
        raise RuntimeError(
            "Cloudinary credentials missing. "
            "Add CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and "
            "CLOUDINARY_API_SECRET to .env"
        )

    public_id = f"switzertemplates/pins/{slug}"
    timestamp = int(time.time())

    sig = _signature({"public_id": public_id, "timestamp": timestamp}, api_secret)

    with open(image_path, "rb") as fh:
        resp = requests.post(
            f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload",
            data={
                "api_key":   api_key,
                "timestamp": timestamp,
                "signature": sig,
                "public_id": public_id,
            },
            files={"file": ("pin.png", fh, "image/png")},
            timeout=60,
        )

    data = resp.json()
    if "secure_url" not in data:
        raise RuntimeError(f"Cloudinary upload failed: {data}")

    return data["secure_url"]


def upload_approved_pins(approved_pins: list[dict]) -> list[dict]:
    """
    Upload all approved pins to Cloudinary.
    Adds 'image_url' to each pin dict in-place. Returns the updated list.
    """
    for pin in approved_pins:
        slug = pin.get("folder", f"pin-{pin.get('index', 0)}")
        image_path = Path(pin["image_path"])
        print(f"  Uploading pin {pin['index']} to Cloudinary...")
        try:
            url = upload_pin(image_path, slug)
            pin["image_url"] = url
            print(f"    {url}")
        except Exception as e:
            print(f"    Upload failed: {e}")
            pin["image_url"] = ""
    return approved_pins
