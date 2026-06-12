from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timezone
from collections import deque
from typing import Any
from datetime import datetime
import json
import os
import pipeline
import db
from services.vehicle_service import lookup_vehicle_by_plate

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
        "run_pipeline": "/run_pipeline",
    }

@app.get("/run_pipeline")
def run_pipeline():
    """
    Executa o pipeline de visão computacional em todos os frames atualmente no buffer.
    Para cada placa detectada, faz a consulta na API da Pier, salva a detecção no banco e imprime o resultado.
    """
    plates = []
    frames_processed = 0

    for frame in frames_buffer:
        if "image_bytes" not in frame:
            continue

        frames_processed += 1
        frame_plates = pipeline.crop_and_read_plates(frame["image_bytes"])

        if frame_plates:
            plates.extend(frame_plates)

    # Faz a consulta para cada placa detectada, salva no banco e imprime o resultado
    for i, (crop, text) in enumerate(plates):
        if not text: continue
        LATITUDE  = -23.5505
        LONGITUDE = -46.6333
        try:
            lookup_response = lookup_vehicle_by_plate(
                text,
                extra_payload={'geolocation': {'latitude': LATITUDE, 'longitude': LONGITUDE}},
            )
            print('Resposta da API (200 - veículo encontrado na Pier):')
            print(lookup_response)

            # claims não-vazio -> veículo roubado/sinistrado -> alert_match=True
            vehicle_data = lookup_response.get('vehicle', {})
            claims = vehicle_data.get('claims', [])
            has_alert = isinstance(claims, list) and len(claims) > 0

            upload, public_url = db.upload_plate_image(
                crop,
                bucket="plates",
                filename=f"{text}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i}.jpg"
            )
            print(public_url)

            if upload.full_path:
                db.save_detection_to_db(
                    text, LATITUDE, LONGITUDE,
                    lookup_response=lookup_response,
                    alert_match=has_alert,
                    image_url=public_url
                )

            if has_alert:
                print('ALERTA: veículo roubado/sinistrado.')
            else:
                print('Veículo encontrado na Pier sem sinistros.')

        except Exception as exc:
            error_text = str(exc)
            if 'status=401' in error_text:
                print('Resposta da API (401): veículo não possui match na Pier. Detecção não salva.')
            elif 'status=404' in error_text and 'VehicleLookup::NotFound' in error_text:
                print('Resposta da API (404): placa não cadastrada na Pier. Detecção não salva.')
            else:
                print('Falha técnica na consulta:')
                print(error_text)

    # Limpa o buffer após processar os frames
    frames_buffer.clear()

    return {
        "message": "Pipeline de visão computacional executada em todos os frames no buffer.",
        "frames_processed": frames_processed,
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

@app.get("/frames/clear")
def clear():
    frames_buffer.clear()
    return {"status": "ok", "message": "Buffer de frames limpo"}

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
            try:
                message = await websocket.receive()
            except (WebSocketDisconnect, RuntimeError):
                print("Cliente desconectado (receive interrompido)")
                break

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

    except WebSocketDisconnect:
        print("Cliente desconectado (outer handler)")