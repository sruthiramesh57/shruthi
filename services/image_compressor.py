"""
Core compression engine.

Strategy: for a given target byte size, first walk down a JPEG/WEBP
quality ladder (cheap — no re-decoding of a resized image needed) since
quality has the biggest effect on file size for the least visual cost.
Only once quality alone bottoms out do we start shrinking dimensions,
because downscaling is the more visually destructive lever and should be
the last resort, not the first.

PNG is a special case: it's lossless, so "quality" doesn't apply the same
way. We first try Pillow's optimizer + palette quantization; if that isn't
enough and the caller allows format changes, we fall back to JPEG/WEBP,
which compress photographic content far better.
"""

import io

from PIL import Image

from config import (
    COMPRESSION_MODES,
    MAX_RESIZE_ITERATIONS,
    MIN_DIMENSION,
    QUALITY_STEPS,
    RESIZE_FACTOR,
)


class CompressionError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class CompressionResult:
    def __init__(self, data, pillow_format, width, height, quality_used, resized, attempts):
        self.data = data
        self.pillow_format = pillow_format
        self.width = width
        self.height = height
        self.quality_used = quality_used
        self.resized = resized
        self.attempts = attempts
        self.size_bytes = len(data)


def _flatten_to_rgb(img, background=(255, 255, 255)):
    """JPEG has no alpha channel. Flattens transparency onto a white
    background instead of letting Pillow silently drop it (which can
    shift colors unpredictably)."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        base = Image.new("RGB", rgba.size, background)
        base.paste(rgba, mask=rgba.split()[-1])
        return base
    return img.convert("RGB")


def _encode(img, pillow_format, quality):
    buf = io.BytesIO()
    save_kwargs = {}
    if pillow_format == "JPEG":
        working = _flatten_to_rgb(img)
        save_kwargs = {"quality": quality, "optimize": True, "progressive": True}
    elif pillow_format == "WEBP":
        working = img.convert("RGB") if img.mode not in ("RGB", "RGBA") else img
        save_kwargs = {"quality": quality, "method": 6}
    elif pillow_format == "PNG":
        working = img
        # PNG "quality" here maps to palette size via quantization done
        # by the caller before this point; optimize does the rest.
        save_kwargs = {"optimize": True}
    else:
        raise CompressionError(f"Unsupported output format: {pillow_format}")

    # Metadata stripping: we build a fresh image buffer and only copy
    # the pixel data (via convert/new above), so EXIF/ICC/XMP chunks
    # from the original file are never written to the output.
    working.save(buf, format=pillow_format, **save_kwargs)
    return buf.getvalue()


def _quantized_png(img, colors):
    return img.convert("P", palette=Image.ADAPTIVE, colors=colors)


def _resize(img, factor):
    new_w = max(MIN_DIMENSION, int(img.width * factor))
    new_h = max(MIN_DIMENSION, int(img.height * factor))
    if (new_w, new_h) == (img.width, img.height):
        return img
    return img.resize((new_w, new_h), Image.LANCZOS)


def compress_to_target(
    image,
    target_bytes,
    mode="balanced",
    output_format=None,
    max_width=None,
    max_height=None,
    fixed_quality=None,
):
    """
    Iteratively compresses `image` (an open Pillow Image) until its
    encoded size is at or below `target_bytes`, or a safety floor is hit.

    Returns a CompressionResult with the best attempt achieved — even if
    the exact target couldn't be reached, so the caller can report an
    honest "closest we could get" rather than pretending success.
    """
    mode_cfg = COMPRESSION_MODES.get(mode, COMPRESSION_MODES["balanced"])
    working = image.copy()

    # Respect explicit max dimensions from Advanced Settings up front.
    if max_width or max_height:
        w, h = working.size
        target_w = max_width or w
        target_h = max_height or h
        scale = min(target_w / w, target_h / h, 1.0)
        if scale < 1.0:
            working = working.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)

    original_format = image.format or "JPEG"
    chosen_format = output_format or (original_format if original_format in ("JPEG", "PNG", "WEBP") else "JPEG")

    attempts = 0
    best = None  # smallest-so-far CompressionResult, used as fallback

    def try_encode(fmt, quality):
        nonlocal attempts, best
        attempts += 1
        img_to_encode = working
        if fmt == "PNG":
            # Map "quality" onto palette size for PNG so the same ladder
            # logic can drive a lossless format too.
            colors = max(16, min(256, int(quality * 2.56)))
            img_to_encode = _quantized_png(working, colors)
        data = _encode(img_to_encode, fmt, quality)
        result = CompressionResult(
            data=data,
            pillow_format=fmt,
            width=working.width,
            height=working.height,
            quality_used=quality,
            resized=(working.size != image.size),
            attempts=attempts,
        )
        if best is None or len(data) < len(best.data):
            best = result
        return result

    # --- Phase 1: quality ladder at original dimensions ---
    quality_steps = [q for q in QUALITY_STEPS if fixed_quality is None or q == fixed_quality] \
        or QUALITY_STEPS
    if fixed_quality is not None:
        quality_steps = [fixed_quality]

    if chosen_format == "PNG" and fixed_quality is None:
        # PNG ladder: start near-lossless and step down palette size.
        quality_steps = [100, 90, 80, 70, 60, 50, 40, 30, mode_cfg["min_quality"]]

    for quality in quality_steps:
        if quality < mode_cfg["min_quality"] and fixed_quality is None:
            break
        result = try_encode(chosen_format, quality)
        if result.size_bytes <= target_bytes:
            return result

    # --- Phase 2: PNG fallback to JPEG/WEBP if still too big and format is free ---
    if chosen_format == "PNG" and output_format is None:
        chosen_format = "JPEG"
        for quality in QUALITY_STEPS:
            if quality < mode_cfg["min_quality"]:
                break
            result = try_encode(chosen_format, quality)
            if result.size_bytes <= target_bytes:
                return result

    # --- Phase 3: progressive resizing, retrying the quality ladder each step ---
    resize_iterations = 0
    while resize_iterations < MAX_RESIZE_ITERATIONS:
        if working.width <= MIN_DIMENSION or working.height <= MIN_DIMENSION:
            break
        working = _resize(working, RESIZE_FACTOR)
        resize_iterations += 1

        floor_quality = mode_cfg["min_quality"] if fixed_quality is None else fixed_quality
        steps = [fixed_quality] if fixed_quality is not None else \
            [q for q in QUALITY_STEPS if q >= floor_quality] or [QUALITY_STEPS[-1]]

        for quality in steps:
            result = try_encode(chosen_format, quality)
            if result.size_bytes <= target_bytes:
                return result

    # Could not fully reach the target without violating quality/size
    # floors. Return the smallest attempt made so the caller can report
    # an honest partial result instead of failing outright.
    if best is None:
        raise CompressionError("Compression failed: no encodable output was produced.")
    return best
