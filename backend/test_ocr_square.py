import sys, os
sys.path.insert(0, os.path.abspath('.'))
from PIL import Image
from app.routers.documents import preprocess_image_for_florence, run_florence_ocr

img_path = "/home/ubuntu/Downloads/Document_Management_System/backend/storage/documents/133b4d91-8d8c-4733-8c03-67fe8c7f7de1.jpg"
image = Image.open(img_path)
image = preprocess_image_for_florence(image)

# Pad to square
w, h = image.size
longest = max(w, h)
new_image = Image.new("RGB", (longest, longest), (255, 255, 255))
new_image.paste(image, ((longest - w) // 2, (longest - h) // 2))

print(f"Square size: {new_image.size}")

try:
    result = run_florence_ocr(new_image)
    print("Success:", result)
except Exception as e:
    import traceback
    traceback.print_exc()
