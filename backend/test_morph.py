import sys
import cv2
import numpy as np
from PIL import Image, ImageOps
import pytesseract

img_path = "storage/documents/e7164486-d1fb-4b36-929c-32065ac8bd09.jpg"
image = Image.open(img_path)
image = ImageOps.exif_transpose(image)
if image.mode not in ("RGB", "L"): image = image.convert("RGB")

min_dimension = 2000
w, h = image.size
longest = max(w, h)
if longest < min_dimension:
    scale = min_dimension / longest
    new_w = int(w * scale)
    new_h = int(h * scale)
    image = image.resize((new_w, new_h), Image.LANCZOS)

open_cv_image = np.array(image)
if len(open_cv_image.shape) == 3:
    open_cv_image = open_cv_image[:, :, ::-1].copy()
    gray = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY)
else:
    gray = open_cv_image

blurred = cv2.GaussianBlur(gray, (5, 5), 0)

binary = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 51, 15)

# Invert to have white text on black background for morphological operations
binary_inv = cv2.bitwise_not(binary)

# Dilate horizontally to connect the dashed lines into solid lines
dilate_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 1))
dilated = cv2.dilate(binary_inv, dilate_kernel, iterations=1)

# Detect horizontal lines (kernel size roughly 1/40th of image width)
kernel_len = max(20, open_cv_image.shape[1] // 40)
horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_len, 1))
horizontal_lines = cv2.morphologyEx(dilated, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)

# We need to make the detected lines a bit thicker to ensure we subtract them entirely
erode_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
horizontal_lines = cv2.dilate(horizontal_lines, erode_kernel, iterations=1)

# Subtract the detected lines from the original inverted image
clean_inv = cv2.subtract(binary_inv, horizontal_lines)

# Revert to black text on white background
clean = cv2.bitwise_not(clean_inv)

print("--- With morphology (lines removed) ---")
print(pytesseract.image_to_string(clean, config="--oem 3 --psm 4").strip()[:300])

