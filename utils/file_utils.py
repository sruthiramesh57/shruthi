"""
Filesystem helpers. The guiding rule: never trust anything derived from
the client (original filename, extension casing, etc.) when building a
path. Every file we write uses a server-generated random name.
"""

import os
import time
import uuid

from config import OUTPUT_DIR, UPLOAD_DIR, FILE_RETENTION_SECONDS

EXT_FOR_FORMAT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


def ensure_directories():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def make_safe_filename(pillow_format):
    """Generates a random, collision-free filename. Never derived from
    user input, so there's nothing to sanitize-and-hope-for-the-best."""
    ext = EXT_FOR_FORMAT.get(pillow_format, "bin")
    return f"{uuid.uuid4().hex}.{ext}"


def safe_join(directory, filename):
    """
    Joins a directory with a filename that must already be a bare name
    (no slashes, no '..'). Rejects anything that would escape the
    directory, which blocks path traversal even if a filename ever
    slipped through with unexpected characters.
    """
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError("Invalid filename")
    full_path = os.path.normpath(os.path.join(directory, filename))
    if not full_path.startswith(os.path.normpath(directory) + os.sep):
        raise ValueError("Path escapes target directory")
    return full_path


def cleanup_expired_files():
    """Removes files older than the retention window from both the
    upload and output directories. Safe to call frequently — it's a
    cheap directory scan, not a recursive walk."""
    now = time.time()
    for directory in (UPLOAD_DIR, OUTPUT_DIR):
        if not os.path.isdir(directory):
            continue
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            try:
                if os.path.isfile(path) and (now - os.path.getmtime(path)) > FILE_RETENTION_SECONDS:
                    os.remove(path)
            except OSError:
                # Another request may have already removed it; not fatal.
                pass


def delete_file_quietly(path):
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def human_readable_size(num_bytes):
    """Formats a byte count the way a user expects to read it (KB/MB)."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.2f} MB"
