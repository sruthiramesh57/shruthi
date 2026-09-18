"""
Central configuration for the Image Size Reducer application.
Keeping these values in one place makes limits easy to audit and tune.
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# Formats we accept and can produce. Pillow calls JPEG output format "JPEG".
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_MIME_PREFIXES = {"image/jpeg", "image/png", "image/webp"}

# Hard ceiling on what a client may upload. Enforced by Flask's
# MAX_CONTENT_LENGTH *and* checked again in validation for defense in depth.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB

# Absolute floor the compressor will not cross, no matter how small the
# requested target is. Prevents "compress to 1 KB" from producing a
# 4x4 pixel smear that is technically a file but useless as an image.
MIN_QUALITY = 10
MIN_DIMENSION = 200  # pixels, on the longer side

# How long a processed file is kept on disk before the cleanup sweep
# removes it. The user downloads within a session, so a short window
# is enough and keeps the output/ directory from growing unbounded.
FILE_RETENTION_SECONDS = 30 * 60  # 30 minutes

# Quality ladder used while iterating. Coarser at the top (quality barely
# affects size there) and finer near the bottom (small changes matter more).
QUALITY_STEPS = [95, 90, 85, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 30, 25, 20, 15, MIN_QUALITY]

# When quality alone can't hit the target even at MIN_QUALITY, the
# dimensions are scaled down by this factor and the quality ladder restarts.
RESIZE_FACTOR = 0.85
MAX_RESIZE_ITERATIONS = 12

TARGET_SIZE_PRESETS = {
    "100kb": 100 * 1024,
    "200kb": 200 * 1024,
    "300kb": 300 * 1024,
    "500kb": 500 * 1024,
    "1mb": 1 * 1024 * 1024,
}

COMPRESSION_MODES = {
    # mode -> starting quality index bias + whether resizing is allowed early
    "best_quality": {"min_quality": 60, "allow_early_resize": False},
    "balanced": {"min_quality": 35, "allow_early_resize": True},
    "max_compression": {"min_quality": MIN_QUALITY, "allow_early_resize": True},
}
