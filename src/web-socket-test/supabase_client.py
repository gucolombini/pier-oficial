import cv2
from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime
import os

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def upload_plate_image(image, bucket: str, filename: str):
    """
    Upload a NumPy/OpenCV image to a Supabase Storage bucket.

    Args:
        image: OpenCV image (numpy.ndarray)
        bucket: Storage bucket name
        filename: File name inside the bucket

    Returns:
        Public URL or upload response
    """

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
    return response