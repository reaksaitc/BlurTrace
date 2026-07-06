"""
algorithms.py
-------------
Core image-processing algorithms for BlurTrace.

Two blur methods (Gaussian blur, Pixelation) + SHA-256 hashing.
These are pure functions with no database or web dependency, so they
can be tested completely on their own before touching FastAPI or Postgres.

All functions work on raw image bytes in -> raw image bytes out (PNG),
which keeps them decoupled from however the bytes arrived (upload, paste,
DB row, etc).
"""

import hashlib
import cv2
import numpy as np


def _bytes_to_cv2_image(image_bytes: bytes) -> np.ndarray:
    """Decode raw image bytes (jpg/png/webp/etc) into an OpenCV BGR image array."""
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image bytes. Unsupported or corrupt file.")
    return img


def _cv2_image_to_png_bytes(img: np.ndarray) -> bytes:
    """Encode an OpenCV BGR image array back into PNG bytes."""
    success, encoded = cv2.imencode(".png", img)
    if not success:
        raise ValueError("Failed to encode image to PNG.")
    return encoded.tobytes()


def _intensity_to_kernel_size(intensity: int) -> int:
    """
    Map a 1-10 intensity slider value to an odd Gaussian kernel size.
    Gaussian kernels must be odd (e.g. 3, 5, 7...) so we clamp and round accordingly.
    Intensity 1 -> small kernel (subtle blur)
    Intensity 10 -> large kernel (heavy blur)
    """
    intensity = max(1, min(10, intensity))
    kernel_size = intensity * 6 + 1  # 1->7, 5->31, 10->61
    if kernel_size % 2 == 0:
        kernel_size += 1
    return kernel_size


def apply_gaussian_blur(image_bytes: bytes, intensity: int) -> bytes:
    """
    Apply Gaussian blur to an image.

    intensity: 1 (subtle) to 10 (heavy).
    Returns PNG-encoded bytes of the blurred image.
    """
    img = _bytes_to_cv2_image(image_bytes)
    k = _intensity_to_kernel_size(intensity)
    blurred = cv2.GaussianBlur(img, (k, k), 0)
    return _cv2_image_to_png_bytes(blurred)


def _intensity_to_pixel_block(intensity: int, width: int, height: int) -> int:
    """
    Map intensity 1-10 to a downscale factor for pixelation.
    Higher intensity -> fewer effective pixels -> chunkier blocks.
    We compute the target small-side dimension as a fraction of the
    smallest image dimension so it scales proportionally regardless of
    original resolution.
    """
    intensity = max(1, min(10, intensity))
    smallest_dim = min(width, height)
    # intensity 1 -> keep ~50% of resolution (light pixelation)
    # intensity 10 -> shrink to ~2% of resolution (heavy pixelation)
    fraction = 0.50 - (intensity - 1) * (0.48 / 9)
    target = max(4, int(smallest_dim * fraction))
    return target


def apply_pixelation(image_bytes: bytes, intensity: int) -> bytes:
    """
    Apply pixelation to an image: downscale then upscale with nearest-neighbor
    interpolation to create the blocky mosaic effect.

    intensity: 1 (subtle) to 10 (heavy).
    Returns PNG-encoded bytes of the pixelated image.
    """
    img = _bytes_to_cv2_image(image_bytes)
    h, w = img.shape[:2]

    small_dim = _intensity_to_pixel_block(intensity, w, h)
    scale = small_dim / min(w, h)
    small_w, small_h = max(1, int(w * scale)), max(1, int(h * scale))

    small = cv2.resize(img, (small_w, small_h), interpolation=cv2.INTER_LINEAR)
    pixelated = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
    return _cv2_image_to_png_bytes(pixelated)


def sha256_hash(data: bytes) -> str:
    """
    Compute the SHA-256 hash of raw bytes, returned as a hex string.
    This is an EXACT-match hash: any change to a single byte produces a
    completely different hash.
    """
    return hashlib.sha256(data).hexdigest()


def sha256_hash_of_pixels(image_bytes: bytes) -> str:
    """
    Compute a SHA-256 hash of an image's DECODED PIXEL DATA, rather than its
    raw file bytes.

    Why this exists: hashing raw file bytes (sha256_hash) breaks whenever an
    image is re-encoded into a different container -- even losslessly, with
    every pixel unchanged. This commonly happens when a user copies a blurred
    image to the OS clipboard and pastes it elsewhere: the OS may round-trip
    it through a bitmap (DIB) representation, producing a PNG with different
    bytes than the one this app originally generated, even though it looks
    pixel-for-pixel identical.

    Hashing the decoded pixel array instead makes the match survive any
    lossless re-encoding (PNG<->BMP<->PNG, etc), because the actual pixel
    values -- not the file format wrapping them -- are what get hashed.

    This is still EXACT matching, just exact on pixels instead of exact on
    file bytes. It does NOT make this a perceptual/fuzzy hash: a lossy
    re-compression (e.g. saving as a low-quality JPEG) still changes pixel
    values slightly and will still produce a different hash. That broader
    fuzzy-matching case remains out of scope for this project.
    """
    img = _bytes_to_cv2_image(image_bytes)
    # Prefix with shape so two different-shaped images can never collide
    # even in the (extremely unlikely) case their raw byte layout matched.
    shape_prefix = f"{img.shape[0]}x{img.shape[1]}x{img.shape[2]}".encode("utf-8")
    return hashlib.sha256(shape_prefix + img.tobytes()).hexdigest()