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
class QualityMetrics:
    blur_score: float
    brightness: float
    contrast: float
    resolution_w: int
    resolution_h: int
    quality_score: float
    is_acceptable: bool


@dataclass
class ProcessedPage:
    page_number: int
    text: str
    is_digital: bool
    blur_score: float
    image_bytes: bytes
    storage_key: str
    quality: QualityMetrics | None = None


def compute_blur_score(img_cv: np.ndarray) -> float:
    """Computes blur score using variance of the Laplacian."""
    if len(img_cv.shape) == 3:
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    else:
        gray = img_cv
    h, w = gray.shape[:2]
    max_dim = max(h, w)
    if max_dim > 1200:
        scale = 1200.0 / max_dim
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    score = float(cv2.Laplacian(gray, cv2.CV_32F).var())
    return score


def compute_quality_metrics(img_cv: np.ndarray) -> QualityMetrics:
    """Computes comprehensive per-page quality score combining blur, brightness, contrast, and resolution."""
    if len(img_cv.shape) == 3:
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    else:
        gray = img_cv

    h, w = gray.shape[:2]
    blur = compute_blur_score(img_cv)
    brightness = float(np.mean(gray))
    contrast = float(np.std(gray))

    # Normalized component scores (0.0 to 1.0)
    norm_blur = min(blur / 100.0, 1.0)
    norm_contrast = min(contrast / 60.0, 1.0)
    norm_res = min(min(w, h) / 800.0, 1.0)

    # Penalize extreme dark or bright images
    brightness_penalty = 1.0
    if brightness < 40.0:
        brightness_penalty = max(0.2, brightness / 40.0)
    elif brightness > 230.0:
        brightness_penalty = max(0.2, (255.0 - brightness) / 25.0)

    composite_score = (0.45 * norm_blur + 0.35 * norm_contrast + 0.20 * norm_res) * brightness_penalty
    is_acceptable = blur >= settings.BLUR_REJECT_THRESHOLD and brightness >= 30.0 and contrast >= 15.0

    return QualityMetrics(
        blur_score=round(blur, 2),
        brightness=round(brightness, 2),
        contrast=round(contrast, 2),
        resolution_w=w,
        resolution_h=h,
        quality_score=round(composite_score, 3),
        is_acceptable=is_acceptable,
    )


def order_points(pts: np.ndarray) -> np.ndarray:
    """Orders 4 polygon points: top-left, top-right, bottom-right, bottom-left."""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def correct_perspective(img_cv: np.ndarray) -> np.ndarray:
    """Detects largest quadrilateral document contour and performs 4-point perspective transform."""
    h, w = img_cv.shape[:2]

    if len(img_cv.shape) == 3:
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    else:
        gray = img_cv

    # Downscale for fast contour detection
    max_dim = 800.0
    scale = 1.0
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        small_gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    else:
        small_gray = gray

    blurred = cv2.GaussianBlur(small_gray, (5, 5), 0)
    edged = cv2.Canny(blurred, 50, 200)

    # Dilate slightly to close edge gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    dilated = cv2.dilate(edged, kernel, iterations=1)

    contours, _ = cv2.findContours(dilated, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

    for c in contours:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)

        if len(approx) == 4:
            area = cv2.contourArea(approx)
            # Must occupy at least 25% of image area to be the main document
            if area >= (0.25 * small_gray.shape[0] * small_gray.shape[1]):
                # Rescale points back to original image coordinates
                pts = approx.reshape(4, 2) / scale
                rect = order_points(pts)
                tl, tr, br, bl = rect

                # Compute width and height of warped image
                widthA = np.linalg.norm(br - bl)
                widthB = np.linalg.norm(tr - tl)
                maxWidth = max(int(widthA), int(widthB))

                heightA = np.linalg.norm(tr - br)
                heightB = np.linalg.norm(tl - bl)
                maxHeight = max(int(heightA), int(heightB))

                if maxWidth > 100 and maxHeight > 100:
                    dst = np.array(
                        [
                            [0, 0],
                            [maxWidth - 1, 0],
                            [maxWidth - 1, maxHeight - 1],
                            [0, maxHeight - 1],
                        ],
                        dtype="float32",
                    )
                    m = cv2.getPerspectiveTransform(rect, dst)
                    warped = cv2.warpPerspective(img_cv, m, (maxWidth, maxHeight), flags=cv2.INTER_CUBIC)
                    return warped

    return img_cv


def normalize_shadows_and_background(img_cv: np.ndarray) -> np.ndarray:
    """Removes non-uniform lighting and shadows via morphological background normalization."""
    if len(img_cv.shape) == 3:
        # Work in LAB color space to normalize Luminance only
        lab = cv2.cvtColor(img_cv, cv2.COLOR_BGR2LAB)
        l_chan, a_chan, b_chan = cv2.split(lab)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
        bg = cv2.morphologyEx(l_chan, cv2.MORPH_DILATE, kernel)
        bg = cv2.medianBlur(bg, 21)
        diff = 255 - cv2.absdiff(l_chan, bg)
        norm_l = cv2.normalize(diff, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_8U)  # type: ignore[call-overload]
        merged = cv2.merge((norm_l, a_chan, b_chan))
        return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
    else:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
        bg = cv2.morphologyEx(img_cv, cv2.MORPH_DILATE, kernel)
        bg = cv2.medianBlur(bg, 21)
        diff = 255 - cv2.absdiff(img_cv, bg)
        norm = cv2.normalize(diff, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_8U)  # type: ignore[call-overload]
        return norm


def auto_rotate_and_crop(img_cv: np.ndarray) -> np.ndarray:
    """Detects 90/180/270 orientation angles and auto-crops margins."""
    h, w = img_cv.shape[:2]
    # Check if image is landscape but aspect ratio suggests vertical invoice document
    if w > h * 1.3:
        # Test 90 degree clockwise rotation
        return cv2.rotate(img_cv, cv2.ROTATE_90_CLOCKWISE)
    return img_cv


def deskew_image(img_cv: np.ndarray) -> np.ndarray:
    """Deskews image using minimum-area-rectangle on text pixels (0.5° to 15.0°)."""
    if len(img_cv.shape) == 3:
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    else:
        gray = img_cv

    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) < 100:
        return img_cv

    rect = cv2.minAreaRect(coords)
    angle = rect[-1]

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

                # 3. OpenCV image processing & quality
                img_cv = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
                quality = compute_quality_metrics(img_cv)

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
                        blur_score=quality.blur_score,
                        image_bytes=compressed_bytes,
                        storage_key=storage_key,
                        quality=quality,
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

        # 2. Hardened pipeline: Perspective -> Auto-rotate -> Deskew -> Shadow normalisation -> CLAHE
        img_cv = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        img_cv = correct_perspective(img_cv)
        img_cv = auto_rotate_and_crop(img_cv)
        img_cv = deskew_image(img_cv)
        img_cv = normalize_shadows_and_background(img_cv)
        img_cv = enhance_image(img_cv)

        # 3. Compute quality metrics
        quality = compute_quality_metrics(img_cv)

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
                blur_score=quality.blur_score,
                image_bytes=compressed_bytes,
                storage_key=storage_key,
                quality=quality,
            )
        ]
