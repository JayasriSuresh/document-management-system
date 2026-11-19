import sys, os
sys.path.insert(0, os.path.abspath('.'))
from PIL import Image
from app.routers.documents import preprocess_image_for_florence, run_florence_ocr

img_path = "/home/ubuntu/Downloads/Document_Management_System/backend/storage/documents/133b4d91-8d8c-4733-8c03-67fe8c7f7de1.jpg"
image = Image.open(img_path)
print(f"Original size: {image.size}")
image = preprocess_image_for_florence(image)
print(f"Preprocessed size: {image.size}")

try:
    result = run_florence_ocr(image)
    print("Success:", result)
except Exception as e:
    import traceback
    traceback.print_exc()
