import os
import json
import time
import websocket
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# URL do WebSocket, definida no arquivo .env
WS_URL = os.getenv("WS_URL", "ws://localhost:8000/ws/frames")

# Diretório onde estão as imagens de teste
IMAGE_DIR = Path("./test_images")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}

# Lê o arquivo de imagem e retorna os bytes
def image_bytes(image_path: Path) -> str:
    with open(image_path, "rb") as f:
        return f.read()

# Constrói o payload de metadata para a imagem
def build_metadata(image_path: Path):
    return {
        "frame_id": int(time.time() * 1000),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "latitude": None,
        "longitude": None,
        "content_type": "image/jpeg",
    }

# Envia as imagens para o WebSocket
def main():
    images = [
        p for p in IMAGE_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]

    if not images:
        raise RuntimeError(f"No images found in {IMAGE_DIR}")

    ws = websocket.create_connection(WS_URL, timeout=10)

    try:
        # Envia todas as imagens da pasta selecionada
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
        # Fecha a conexão WebSocket quando terminar o envio dos pacotes
        ws.close()


if __name__ == "__main__":
    main()