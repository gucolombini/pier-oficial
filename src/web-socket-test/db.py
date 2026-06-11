from pathlib import Path
import sys
import os
import psycopg2
from supabase import create_client
import cv2
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def upload_plate_image(image, bucket: str, filename: str):
    success, buffer = cv2.imencode(".jpg", image)

    if not success:
        raise ValueError("Failed to encode image")

    image_bytes = buffer.tobytes()

    response = supabase.storage.from_(bucket).upload(
        path=filename,
        file=image_bytes,
        file_options={
            "content-type": "image/jpeg",
            "upsert": "true",
        },
    )

    public_url = supabase.storage.from_(bucket).get_public_url(filename)

    return response, public_url

# Sobe a árvore de diretórios até encontrar a pasta que contém 'src'
repo_root = Path.cwd()
for _ in range(5):
    if (repo_root / 'src').exists():
        break
    repo_root = repo_root.parent

src_path = repo_root / 'src'
if str(src_path) not in sys.path:
    sys.path.append(str(src_path))

def _db_connect():
    ssl_mode = 'require' if os.getenv('DB_SSL', '').lower() == 'true' else 'disable'
    return psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=int(os.getenv('DB_PORT', 5432)),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        dbname=os.getenv('DB_DATABASE'),
        sslmode=ssl_mode,
    )

def save_detection_to_db(plate_text, latitude, longitude, lookup_response, alert_match=False, image_url=None):
    """Salva apenas veículos com match confirmado na API da Pier.
    alert_match=True → veículo possui sinistros registrados (vehicle.claims não-vazio).
    """
    def _lower_or_none(val):
        s = str(val).strip() if val is not None else ''
        return s.lower() if s else None

    license_plate = plate_text.upper()

    vehicle_data = lookup_response.get('vehicle', {})
    vehicle_brand = _lower_or_none(vehicle_data.get('make'))
    vehicle_model = _lower_or_none(vehicle_data.get('model'))
    vehicle_color = _lower_or_none(vehicle_data.get('color'))

    conn = _db_connect()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO vehicle (license_plate, vehicle_model, vehicle_brand, vehicle_color)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (license_plate) DO NOTHING
                    """,
                    (license_plate, vehicle_model, vehicle_brand, vehicle_color),
                )

                cur.execute("SELECT id FROM operation ORDER BY id DESC LIMIT 1")
                row = cur.fetchone()
                if row is None:
                    print('Aviso: nenhuma operação encontrada no banco. Detecção não salva.')
                    return None
                operation_id = row[0]

                cur.execute(
                    """
                    INSERT INTO detection (operation_id, license_plate, latitude, longitude, pier_match, alert_match, image_url)
                    VALUES (%s, %s, %s, %s, TRUE, %s, %s)
                    RETURNING id
                    """,
                    (operation_id, license_plate, latitude, longitude, alert_match, image_url),
                )
                return cur.fetchone()[0]
    finally:
        conn.close()