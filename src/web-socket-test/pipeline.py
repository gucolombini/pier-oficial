from ultralytics import YOLO
import cv2

def run_yolo():
    model = YOLO("best.pt")
    image_path = "manycars.jpg"
    results = model(image_path)
    image = cv2.imread(image_path)

    boxes = results[0].boxes
    plates = []

    for i in range(len(boxes)):
        class_id = int(boxes.cls[i])
        if class_id == 0:
            x1, y1, x2, y2 = map(int, boxes.xyxy[i])
            crop = image[y1:y2, x1:x2]
            plates.append(crop)
            print(f"Saved crop_{i}.jpg")
    return plates