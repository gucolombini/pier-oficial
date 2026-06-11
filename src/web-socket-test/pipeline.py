from ultralytics import YOLO
import numpy as np
import cv2
from fast_plate_ocr import LicensePlateRecognizer

recognizer = LicensePlateRecognizer(
    onnx_model_path="ocr/best.onnx",
    plate_config_path="ocr/config/plate_config.yaml",
)

def read_plate_from_image(img):
    plate = ""
    result = recognizer.run(img)
    if len(result[0].plate) == 7:
        letters = result[0].plate[:3]
        numbers = result[0].plate[3:]
        plate = f"{letters} {numbers}"
    return plate

yolo_plate_model = YOLO("best.pt")

def crop_and_read_plates(img_bytes) -> list:
    
    image = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    results = yolo_plate_model(image)

    boxes = results[0].boxes
    output = []

    for i in range(len(boxes)):
        class_id = int(boxes.cls[i])

        if class_id == 0:
            x1, y1, x2, y2 = map(int, boxes.xyxy[i])

            crop = image[y1:y2, x1:x2]
            text = read_plate_from_image(crop)

            output.append((crop, text))

    return output