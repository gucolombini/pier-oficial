from ultralytics import YOLO
import numpy as np
import cv2
from fast_plate_ocr import LicensePlateRecognizer

# Carrega arquivo .onxx do melhor modelo de OCR
recognizer = LicensePlateRecognizer(
    onnx_model_path="models/ocr/best.onnx",
    plate_config_path="models/ocr/config/plate_config.yaml",
)

# Executa o OCR na placa recortada e retorna o texto da placa se for válida
def read_plate_from_image(img):
    plate = ""
    result = recognizer.run(img)
    # Verifica se o resultado tem uma placa válida (7 caracteres)
    if len(result[0].plate) == 7:
        letters = result[0].plate[:3]
        numbers = result[0].plate[3:]
        plate = f"{letters} {numbers}"
    return plate

# Carrega o modelo YOLO para detecção de placas
yolo_plate_model_path = "models/yolo/plate.pt" 
yolo_plate_model = YOLO(yolo_plate_model_path)

def crop_and_read_plates(img_bytes) -> list:
    
    # Converte os bytes da imagem para formato OpenCV
    image = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)

    # Executa a detecção de placas usando o modelo YOLO, retornando as caixas de cada placa
    results = yolo_plate_model(image)
    boxes = results[0].boxes
    output = []

    for i in range(len(boxes)):
        class_id = int(boxes.cls[i])

        # !!! Selecionar id de classe correspondente a placas (0 no modelo atual) !!!
        if class_id == 0:
            x1, y1, x2, y2 = map(int, boxes.xyxy[i])

            crop = image[y1:y2, x1:x2]
            text = read_plate_from_image(crop)

            output.append((crop, text))

    return output