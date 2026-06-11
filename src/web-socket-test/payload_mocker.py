import os
import json
import time
from pathlib import Path
from datetime import datetime, timezone

import websocket
from dotenv import load_dotenv

load_dotenv()

WS_URL = os.getenv("WS_URL")

IMAGE_DIR = Path("./test_images")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def image_bytes(image_path: Path) -> str:
    with open(image_path, "rb") as f:
        return f.read()


def build_metadata(image_path: Path):
    return {
        "frame_id": int(time.time() * 1000),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "latitude": None,
        "longitude": None,
        "content_type": "image/jpeg",
    }


def main():
    images = [
        p for p in IMAGE_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]

    if not images:
        raise RuntimeError(f"No images found in {IMAGE_DIR}")

    ws = websocket.create_connection(WS_URL, timeout=10)

    try:
        for i, image_path in enumerate(images, start=1):
            metadata = build_metadata(image_path)
            img_bytes = image_bytes(image_path)

            print(
                f"[{i}/{len(images)}] Sending {image_path.name} "
                f"({len(img_bytes) / 1024:.1f} KB)"
            )

            ws.send(json.dumps(metadata))
            ws.send_binary(img_bytes)

            try:
                response = ws.recv()
                print("Response:", response)
            except Exception as e:
                print("No response:", e)

            time.sleep(0.5)

    finally:
        ws.close()


if __name__ == "__main__":
    main()