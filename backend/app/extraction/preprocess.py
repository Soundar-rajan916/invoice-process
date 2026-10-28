from __future__ import annotations

import io
from dataclasses import dataclass

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageOps

from app.core.config import settings
from app.core.storage import storage_service


@dataclass
class ProcessedPage:
    page_number: int
    text: str
    is_digital: bool
    blur_score: float
    image_bytes: bytes
    storage_key: str


def compute_blur_score(img_cv: np.ndarray) -> float:
    """Computes blur score using variance of the Laplacian."""
    if len(img_cv.shape) == 3:
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    else:
        gray = img_cv
    score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    return score


def deskew_image(img_cv: np.ndarray) -> np.ndarray:
    """Deskews image using minimum-area-rectangle on text pixels.
    Corrects only when angle is between 0.5° and 15.0°.
    """
    if len(img_cv.shape) == 3:
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    else:
        gray = img_cv

    # Invert and threshold to find text pixels
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) < 100:
        return img_cv

    rect = cv2.minAreaRect(coords)
    angle = rect[-1]

    # Normalize angle
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    if 0.5 <= abs(angle) <= 15.0:
        h, w = img_cv.shape[:2]
        center = (w // 2, h // 2)
        m = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(
            img_cv, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )
        return rotated
    return img_cv


def enhance_image(img_cv: np.ndarray) -> np.ndarray:
    """Applies mild denoising and contrast normalization (CLAHE)."""
    # 1. CLAHE in LAB color space
    if len(img_cv.shape) == 3:
        lab = cv2.cvtColor(img_cv, cv2.COLOR_BGR2LAB)
        l_chan, a_chan, b_chan = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        cl = clahe.apply(l_chan)
        limg = cv2.merge((cl, a_chan, b_chan))
        enhanced = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
    else:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(img_cv)

    # 2. Mild bilateral filter denoising
    denoised = cv2.bilateralFilter(enhanced, d=5, sigmaColor=50, sigmaSpace=50)
    return denoised


def downscale_and_compress(pil_img: Image.Image, max_long_side: int, quality: int = 85) -> bytes:
    """Downscales image so long side is at most max_long_side, then JPEG compresses."""
    w, h = pil_img.size
    long_side = max(w, h)
    if long_side > max_long_side:
        scale = max_long_side / float(long_side)
        new_w, new_h = int(w * scale), int(h * scale)
        pil_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    if pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")
    pil_img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


class Preprocessor:
    def __init__(self, invoice_id: str = "eval") -> None:
        self.invoice_id = invoice_id
        self.min_text_chars = settings.MIN_TEXT_CHARS
        self.max_long_side = settings.MAX_IMAGE_LONG_SIDE
        self.blur_threshold = settings.BLUR_REJECT_THRESHOLD

    def process(self, raw_bytes: bytes, content_type: str) -> list[ProcessedPage]:
        """Preprocesses a PDF or image into a list of ProcessedPage objects."""
        if content_type == "application/pdf":
            return self._process_pdf(raw_bytes)
        else:
            return self._process_image(raw_bytes)

    def _process_pdf(self, pdf_bytes: bytes) -> list[ProcessedPage]:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages: list[ProcessedPage] = []

        try:
            for page_idx in range(len(doc)):
                page = doc[page_idx]
                page_num = page_idx + 1

                # 1. Text layer extraction
                text = page.get_text("text").strip()
                is_digital = len(text) >= self.min_text_chars

                # 2. Render to JPEG at ~200 DPI (zoom 200/72 = 2.77)
                zoom = 200.0 / 72.0
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                pil_img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

                # 3. Compute blur score via OpenCV
                img_cv = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
                blur_score = compute_blur_score(img_cv)

                # 4. Downscale and compress
                compressed_bytes = downscale_and_compress(pil_img, self.max_long_side, quality=85)

                # 5. Store in MinIO under pages/{invoice_id}/{n}.jpg
                storage_key = f"pages/{self.invoice_id}/{page_num}.jpg"
                storage_service.upload_bytes(
                    compressed_bytes, storage_key, content_type="image/jpeg"
                )

                pages.append(
                    ProcessedPage(
                        page_number=page_num,
                        text=text,
                        is_digital=is_digital,
                        blur_score=blur_score,
                        image_bytes=compressed_bytes,
                        storage_key=storage_key,
                    )
                )
        finally:
            doc.close()

        return pages

    def _process_image(self, img_bytes: bytes) -> list[ProcessedPage]:
        raw_img = Image.open(io.BytesIO(img_bytes))

        # 1. EXIF auto-orient & convert to RGB
        pil_img: Image.Image = ImageOps.exif_transpose(raw_img) or raw_img
        if pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")

        # 2. Deskew and enhance with OpenCV
        img_cv = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        img_cv = deskew_image(img_cv)
        img_cv = enhance_image(img_cv)

        # 3. Compute blur score
        blur_score = compute_blur_score(img_cv)

        # 4. Downscale and compress
        pil_enhanced = Image.fromarray(cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB))
        compressed_bytes = downscale_and_compress(pil_enhanced, self.max_long_side, quality=85)

        # 5. Store in MinIO
        storage_key = f"pages/{self.invoice_id}/1.jpg"
        storage_service.upload_bytes(compressed_bytes, storage_key, content_type="image/jpeg")

        return [
            ProcessedPage(
                page_number=1,
                text="",
                is_digital=False,
                blur_score=blur_score,
                image_bytes=compressed_bytes,
                storage_key=storage_key,
            )
        ]
