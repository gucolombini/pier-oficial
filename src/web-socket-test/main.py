from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timezone
from collections import deque
from typing import Any
import json
import os
import pipeline
import supabase_client

app = FastAPI(title="Pier Drone Backend")

# O Render deve usar Root Directory = src/web-socket-test.
# Por isso, a pasta static é referenciada diretamente como "static".
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRAME_BUFFER_SIZE = 100
frames_buffer = deque(maxlen=FRAME_BUFFER_SIZE)

latest_metadata: dict[str, Any] = {}
frame_counter = 0

MOCK_SINISTROS = {
    "ABC1D23": {
        "status": "roubado",
        "modelo": "Honda Civic",
        "cor": "preto",
    },
    "XYZ9A87": {
        "status": "furtado",
        "modelo": "Toyota Corolla",
        "cor": "prata",
    },
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_latest_frame() -> dict[str, Any] | None:
    if not frames_buffer:
        return None
    return frames_buffer[-1]


@app.get("/")
def root():
    return {
        "message": "Pier Drone Backend online",
        "status": "ok",
        "websocket": "/ws/frames",
        "mobile_client": "/static/mobile-client.html",
        "viewer": "/static/viewer.html",
        "vision_latest_frame": "/vision/latest-frame",
        "vision_latest_frame_meta": "/vision/latest-frame/meta",
    }

@app.get("/predict")
def predict():
    plates = pipeline.run_yolo()
    for i, plate in enumerate(plates):
        # Exemplo de upload, idealmente seria cada crop individual
        supabase_client.upload_plate_image(plate, bucket="plates", filename=f"plate_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i}.jpg")
    return {
        "message": "Rota de teste para rodar o pipeline de visão computacional",
        "plates_detected": len(plates),
    }


@app.get("/health")
def health():
    latest_frame = get_latest_frame()

    return {
        "status": "online",
        "timestamp": utc_now_iso(),
        "buffer_size": len(frames_buffer),
        "max_buffer_size": FRAME_BUFFER_SIZE,
        "latest_frame_id": latest_frame["frame_id"] if latest_frame else None,
    }


@app.get("/frames/latest")
def get_latest_frames():
    """
    Retorna metadados dos últimos frames recebidos.
    Não retorna a imagem para evitar resposta pesada.
    """
    return {
        "total": len(frames_buffer),
        "frames": [
            {
                "frame_id": frame["frame_id"],
                "timestamp": frame["timestamp"],
                "latitude": frame.get("latitude"),
                "longitude": frame.get("longitude"),
                "content_type": frame.get("content_type"),
                "size_bytes": frame.get("size_bytes"),
                "received_at": frame["received_at"],
            }
            for frame in list(frames_buffer)[-10:]
        ],
    }


@app.get("/frames/latest/image")
def get_latest_frame_image():
    """
    Rota antiga mantida por compatibilidade.
    Retorna a imagem do último frame recebido em bytes.
    """
    latest_frame = get_latest_frame()

    if latest_frame is None:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Nenhum frame recebido ainda"},
        )

    return Response(
        content=latest_frame["image_bytes"],
        media_type=latest_frame.get("content_type") or "image/jpeg",
        headers={
            "X-Frame-Id": str(latest_frame["frame_id"]),
            "X-Timestamp": str(latest_frame["timestamp"]),
            "X-Size-Bytes": str(latest_frame["size_bytes"]),
        },
    )


@app.get("/vision/latest-frame")
def vision_latest_frame():
    """
    Rota principal para o modelo de visão computacional consultar
    a imagem mais recente recebida do drone/celular.
    """
    return get_latest_frame_image()


@app.get("/vision/latest-frame/meta")
def vision_latest_frame_meta():
    """
    Retorna apenas os metadados do último frame, sem baixar a imagem.
    """
    latest_frame = get_latest_frame()

    if latest_frame is None:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Nenhum frame recebido ainda"},
        )

    return {
        "frame_id": latest_frame["frame_id"],
        "timestamp": latest_frame["timestamp"],
        "latitude": latest_frame.get("latitude"),
        "longitude": latest_frame.get("longitude"),
        "content_type": latest_frame.get("content_type"),
        "size_bytes": latest_frame.get("size_bytes"),
        "received_at": latest_frame.get("received_at"),
        "image_url": "/vision/latest-frame",
    }


@app.get("/vision/frames/count")
def vision_frames_count():
    latest_frame = get_latest_frame()

    return {
        "buffer_size": len(frames_buffer),
        "max_buffer_size": FRAME_BUFFER_SIZE,
        "latest_frame_id": latest_frame["frame_id"] if latest_frame else None,
    }


@app.get("/vision/frames/{frame_id}")
def vision_frame_by_id(frame_id: int):
    for frame in frames_buffer:
        if int(frame["frame_id"]) == frame_id:
            return Response(
                content=frame["image_bytes"],
                media_type=frame.get("content_type") or "image/jpeg",
                headers={
                    "X-Frame-Id": str(frame["frame_id"]),
                    "X-Timestamp": str(frame["timestamp"]),
                    "X-Size-Bytes": str(frame["size_bytes"]),
                },
            )

    return JSONResponse(
        status_code=404,
        content={"status": "error", "message": f"Frame {frame_id} não encontrado"},
    )


@app.get("/sinistros/{placa}")
def consultar_sinistro(placa: str):
    placa = placa.upper()

    if placa in MOCK_SINISTROS:
        return {
            "match": True,
            "placa": placa,
            "dados": MOCK_SINISTROS[placa],
        }

    return {
        "match": False,
        "placa": placa,
        "dados": None,
    }


@app.websocket("/ws/frames")
async def websocket_frames(websocket: WebSocket):
    """
    Recebe metadados em JSON via mensagem de texto e a imagem via bytes.

    Fluxo esperado do cliente:
    1. websocket.send(JSON.stringify(metadata))
    2. websocket.send(arrayBuffer_da_imagem)
    """
    global latest_metadata, frame_counter

    await websocket.accept()
    print("Cliente conectado ao WebSocket")

    try:
        while True:
            message = await websocket.receive()

            if message.get("text") is not None:
                try:
                    latest_metadata = json.loads(message["text"])
                except json.JSONDecodeError:
                    await websocket.send_json({
                        "status": "error",
                        "message": "JSON de metadados inválido",
                    })
                continue

            if message.get("bytes") is not None:
                image_bytes = message["bytes"]
                frame_counter += 1

                frame_id = latest_metadata.get("frame_id") or frame_counter
                timestamp = latest_metadata.get("timestamp") or utc_now_iso()

                frame_data = {
                    "frame_id": frame_id,
                    "timestamp": timestamp,
                    "latitude": latest_metadata.get("latitude"),
                    "longitude": latest_metadata.get("longitude"),
                    "content_type": latest_metadata.get("content_type", "image/jpeg"),
                    "size_bytes": len(image_bytes),
                    "image_bytes": image_bytes,
                    "received_at": utc_now_iso(),
                }

                frames_buffer.append(frame_data)

                await websocket.send_json({
                    "status": "ok",
                    "message": "frame recebido em bytes",
                    "frame_id": frame_id,
                    "size_bytes": len(image_bytes),
                    "buffer_size": len(frames_buffer),
                })

                print(
                    f"Frame recebido: {frame_id} | "
                    f"{len(image_bytes)} bytes | Buffer: {len(frames_buffer)}"
                )

    except WebSocketDisconnect:
        print("Cliente desconectado do WebSocket")
