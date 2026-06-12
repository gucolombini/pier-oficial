import time
import base64
import json
from pathlib import Path
from datetime import datetime, timezone

import websocket

WS_URL = "wss://pier-test-websocket.onrender.com/ws/frames"

# Pasta que será monitorada no celular
WATCH_DIR = Path.home() / "storage" / "shared" / "PierFrames"

# Extensões aceitas
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}

sent_files = set()


def image_to_base64(image_path: Path) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def send_image(image_path: Path):
    image_base64 = image_to_base64(image_path)

    payload = {
        "frame_id": int(time.time() * 1000),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "latitude": None,
        "longitude": None,
        "image": image_base64
    }

    ws = websocket.create_connection(WS_URL, timeout=10)
    ws.send(json.dumps(payload))

    response = ws.recv()
    print("Resposta do backend:", response)

    ws.close()


def main():
    print("=== Pier Termux Gateway ===")
    print(f"Monitorando pasta: {WATCH_DIR}")
    print(f"Enviando para: {WS_URL}")
    print("Aguardando imagens...\n")

    if not WATCH_DIR.exists():
        print("Pasta não encontrada. Criando pasta...")
        WATCH_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        images = sorted([
            file for file in WATCH_DIR.iterdir()
            if file.is_file() and file.suffix.lower() in IMAGE_EXTENSIONS
        ])

        for image_path in images:
            if image_path in sent_files:
                continue

            try:
                print(f"Nova imagem encontrada: {image_path.name}")

                # Pequena espera para garantir que o arquivo terminou de salvar
                time.sleep(0.5)

                send_image(image_path)

                sent_files.add(image_path)
                print(f"Imagem enviada com sucesso: {image_path.name}\n")

            except Exception as error:
                print(f"Erro ao enviar {image_path.name}: {error}\n")

        time.sleep(1)


if __name__ == "__main__":
    main()