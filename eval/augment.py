from __future__ import annotations

import math
import random
from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image


def augment_image(
    image: np.ndarray,
    seed: int = 42,
    perspective: bool = True,
    rotation: bool = True,
    shadow: bool = True,
    blur: bool = True,
    jpeg_quality: int = 70,
) -> np.ndarray:
    """Deterministically transforms a clean document image into a realistic phone photo capture.
    R1: Simulates camera phone capture (perspective skew, slight rotation, uneven shadows, mild blur, compression).
    """
    rng = np.random.RandomState(seed)
    py_rng = random.Random(seed)

    h, w = image.shape[:2]
    result = image.copy()

    # 1. Perspective skew (simulate tilted camera)
    if perspective:
        dx = w * rng.uniform(0.01, 0.04)
        dy = h * rng.uniform(0.01, 0.04)

        src_pts = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
        dst_pts = np.array(
            [
                [rng.uniform(0, dx), rng.uniform(0, dy)],
                [w - rng.uniform(0, dx), rng.uniform(0, dy)],
                [w - rng.uniform(0, dx), h - rng.uniform(0, dy)],
                [rng.uniform(0, dx), h - rng.uniform(0, dy)],
            ],
            dtype=np.float32,
        )
        matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
        result = cv2.warpPerspective(
            result, matrix, (w, h), borderMode=cv2.BORDER_CONSTANT, borderValue=(240, 240, 240)
        )

    # 2. Slight rotation (-2 to +2 degrees)
    if rotation:
        angle = rng.uniform(-2.5, 2.5)
        center = (w // 2, h // 2)
        rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
        result = cv2.warpAffine(
            result, rot_mat, (w, h), borderMode=cv2.BORDER_CONSTANT, borderValue=(240, 240, 240)
        )

    # 3. Shadow gradient (simulates overhead lighting / phone shadow)
    if shadow:
        angle_rad = rng.uniform(0, 2 * math.pi)
        # Create 2D gradient mesh
        x = np.linspace(-1, 1, w)
        y = np.linspace(-1, 1, h)
        xx, yy = np.meshgrid(x, y)
        proj = xx * math.cos(angle_rad) + yy * math.sin(angle_rad)
        # Normalize to [0.65, 1.0] illumination multiplier
        proj_norm = (proj - proj.min()) / (proj.max() - proj.min() + 1e-6)
        illum = 0.65 + 0.35 * proj_norm

        if len(result.shape) == 3:
            illum = np.repeat(illum[:, :, np.newaxis], 3, axis=2)

        shaded = (result.astype(np.float32) * illum).clip(0, 255).astype(np.uint8)
        result = shaded

    # 4. Mild blur (variance of camera focus)
    if blur:
        k_size = py_rng.choice([3, 5])
        sigma = rng.uniform(0.6, 1.2)
        result = cv2.GaussianBlur(result, (k_size, k_size), sigma)

    # 5. JPEG compression artifacts
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality]
    _, encimg = cv2.imencode(".jpg", result, encode_param)
    decompressed = cv2.imdecode(encimg, 1)
    if decompressed is not None:
        return np.asarray(decompressed, dtype=np.uint8)

    return result


def augment_pdf_page(
    pdf_path: str | Path,
    page_number: int = 0,
    dpi: int = 200,
    seed: int = 42,
) -> np.ndarray:
    """Renders a PDF page and applies phone-photo degradation."""
    doc = fitz.open(str(pdf_path))
    if page_number >= len(doc):
        page_number = 0
    page = doc[page_number]

    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    doc.close()

    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    img_np = np.array(img)
    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

    return augment_image(img_bgr, seed=seed)


def create_augmented_file(
    input_pdf_path: str | Path,
    output_image_path: str | Path,
    seed: int = 42,
) -> Path:
    """Generates an augmented JPG file from an input PDF file."""
    out_path = Path(output_image_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    augmented_bgr = augment_pdf_page(input_pdf_path, seed=seed)
    cv2.imwrite(str(out_path), augmented_bgr)
    return out_path
