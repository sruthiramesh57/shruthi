"""
Validation helpers. Everything the browser sends is treated as untrusted:
extension, declared mimetype, and the file contents are all checked
independently before anything touches Pillow or the filesystem.
"""

from PIL import Image, UnidentifiedImageError

from config import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, TARGET_SIZE_PRESETS


class ValidationError(Exception):
    """Raised for any user-facing input problem. The message is safe to
    show directly to the client — never put internal details in here."""

    def __init__(self, message, field=None):
        super().__init__(message)
        self.message = message
        self.field = field


def get_extension(filename):
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def validate_extension(filename):
    ext = get_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"Unsupported file format '.{ext or '?'}'. "
            f"Please upload a JPG, PNG, or WEBP image.",
            field="file",
        )
    return ext


def validate_file_size(size_bytes):
    if size_bytes <= 0:
        raise ValidationError("The uploaded file is empty.", field="file")
    if size_bytes > MAX_UPLOAD_BYTES:
        mb = MAX_UPLOAD_BYTES / (1024 * 1024)
        raise ValidationError(
            f"File is too large. Maximum upload size is {mb:.0f} MB.",
            field="file",
        )


def validate_image_content(file_stream):
    """
    Confirms the bytes are actually a decodable image, regardless of what
    the extension or Content-Type header claimed. Returns the detected
    Pillow format (e.g. 'JPEG', 'PNG', 'WEBP') and resets the stream
    position so the caller can read it again.
    """
    try:
        file_stream.seek(0)
        with Image.open(file_stream) as img:
            img.verify()  # cheap structural check
        file_stream.seek(0)
        with Image.open(file_stream) as img:
            img.load()  # force full decode to catch truncated/corrupt data
            detected_format = img.format
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationError(
            "The uploaded file is not a valid image, or the image data is corrupted.",
            field="file",
        )
    finally:
        file_stream.seek(0)

    if detected_format not in ("JPEG", "PNG", "WEBP"):
        raise ValidationError(
            f"Detected image type '{detected_format or 'unknown'}' is not supported. "
            f"Please upload a JPG, PNG, or WEBP image.",
            field="file",
        )
    return detected_format


def parse_target_size(target_size_raw, target_unit_raw):
    """
    Accepts either a preset key (e.g. '200kb') or a custom numeric value
    plus a unit ('kb' or 'mb'). Returns the target size in bytes.
    """
    if not target_size_raw:
        raise ValidationError("Please choose a target size.", field="target_size")

    preset_key = str(target_size_raw).strip().lower()
    if preset_key in TARGET_SIZE_PRESETS:
        return TARGET_SIZE_PRESETS[preset_key]

    # Custom size path
    try:
        value = float(target_size_raw)
    except (TypeError, ValueError):
        raise ValidationError("Custom target size must be a number.", field="target_size")

    if value <= 0:
        raise ValidationError("Custom target size must be greater than zero.", field="target_size")

    unit = (target_unit_raw or "kb").strip().lower()
    if unit not in ("kb", "mb"):
        raise ValidationError("Target size unit must be KB or MB.", field="target_unit")

    size_bytes = value * (1024 * 1024 if unit == "mb" else 1024)

    if size_bytes < 5 * 1024:
        raise ValidationError(
            "Target size is too small to produce a usable image (minimum 5 KB).",
            field="target_size",
        )
    if size_bytes > MAX_UPLOAD_BYTES:
        raise ValidationError("Target size can't be larger than the maximum upload size.", field="target_size")

    return int(size_bytes)


def validate_compression_mode(mode):
    from config import COMPRESSION_MODES

    mode = (mode or "balanced").strip().lower()
    if mode not in COMPRESSION_MODES:
        raise ValidationError(
            "Invalid compression mode. Choose Best Quality, Balanced, or Maximum Compression.",
            field="mode",
        )
    return mode


def validate_output_format(output_format):
    if not output_format or output_format.lower() == "auto":
        return None
    fmt = output_format.strip().lower()
    mapping = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}
    if fmt not in mapping:
        raise ValidationError("Invalid output format requested.", field="output_format")
    return mapping[fmt]


def validate_dimension(value, name):
    if value in (None, "", "0"):
        return None
    try:
        dim = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{name} must be a whole number of pixels.", field=name)
    if dim <= 0 or dim > 10000:
        raise ValidationError(f"{name} must be between 1 and 10000 pixels.", field=name)
    return dim


def validate_quality(value):
    if value in (None, "", "auto"):
        return None
    try:
        q = int(value)
    except (TypeError, ValueError):
        raise ValidationError("JPEG quality must be a whole number between 1 and 100.", field="quality")
    if q < 1 or q > 100:
        raise ValidationError("JPEG quality must be between 1 and 100.", field="quality")
    return q
