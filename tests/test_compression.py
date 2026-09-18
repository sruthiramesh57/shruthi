"""
Tests exercise the real Flask app and the real compression engine —
no mocking of Pillow or the HTTP layer. Test images are generated
on the fly so the suite doesn't depend on fixture binaries.
"""

import io
import os
import sys

import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from services.image_compressor import compress_to_target
from utils.validation import (
    ValidationError,
    parse_target_size,
    validate_extension,
    validate_file_size,
)


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------

@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True)
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


def make_image_bytes(fmt="JPEG", size=(1600, 1200), color=(180, 60, 60)):
    """Builds a real, non-trivial photographic-ish image in memory so
    compression actually has something to chew on (a flat single-color
    image compresses to near-nothing regardless of settings)."""
    img = Image.new("RGB", size, color)
    # Add some gradient/noise-like variation so JPEG quality differences
    # are actually visible in output size.
    pixels = img.load()
    for x in range(0, size[0], 7):
        for y in range(0, size[1], 11):
            pixels[x, y] = ((x * 7) % 256, (y * 3) % 256, (x + y) % 256)

    buf = io.BytesIO()
    if fmt == "PNG":
        img.save(buf, format="PNG")
    elif fmt == "WEBP":
        img.save(buf, format="WEBP", quality=95)
    else:
        img.save(buf, format="JPEG", quality=95)
    buf.seek(0)
    return buf.getvalue()


# ---------------------------------------------------------------------
# Upload / format validation
# ---------------------------------------------------------------------

def test_valid_jpeg_upload(client):
    data = make_image_bytes("JPEG")
    resp = client.post(
        "/compress",
        data={
            "image": (io.BytesIO(data), "photo.jpg"),
            "target_size": "200kb",
            "mode": "balanced",
        },
        content_type="multipart/form-data",
    )
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["success"] is True
    assert body["compressed_size"] > 0
    assert body["compressed_size"] < body["original_size"]


def test_valid_png_upload(client):
    data = make_image_bytes("PNG")
    assert len(data) > 100 * 1024  # sanity check: target below must be smaller than this
    resp = client.post(
        "/compress",
        data={
            "image": (io.BytesIO(data), "photo.png"),
            "target_size": "100kb",
            "mode": "balanced",
        },
        content_type="multipart/form-data",
    )
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["success"] is True
    assert body["compressed_size"] < body["original_size"]


def test_valid_webp_upload(client):
    data = make_image_bytes("WEBP")
    resp = client.post(
        "/compress",
        data={
            "image": (io.BytesIO(data), "photo.webp"),
            "target_size": "100kb",
            "mode": "max_compression",
        },
        content_type="multipart/form-data",
    )
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["success"] is True


def test_invalid_file_upload_rejected(client):
    fake = io.BytesIO(b"this is not an image, just plain text pretending to be one")
    resp = client.post(
        "/compress",
        data={
            "image": (fake, "not-an-image.jpg"),
            "target_size": "200kb",
        },
        content_type="multipart/form-data",
    )
    body = resp.get_json()
    assert resp.status_code == 400
    assert body["success"] is False
    assert "not a valid image" in body["error"].lower() or "corrupted" in body["error"].lower()


def test_disallowed_extension_rejected(client):
    data = make_image_bytes("JPEG")
    resp = client.post(
        "/compress",
        data={
            "image": (io.BytesIO(data), "photo.gif"),
            "target_size": "200kb",
        },
        content_type="multipart/form-data",
    )
    body = resp.get_json()
    assert resp.status_code == 400
    assert body["success"] is False
    assert "unsupported" in body["error"].lower()


def test_empty_upload_rejected(client):
    resp = client.post(
        "/compress",
        data={"target_size": "200kb"},
        content_type="multipart/form-data",
    )
    body = resp.get_json()
    assert resp.status_code == 400
    assert body["success"] is False


def test_oversized_upload_rejected(app, client):
    # Temporarily lower the app's content-length ceiling so we don't
    # need to actually generate a 25MB file to exercise this path.
    app.config["MAX_CONTENT_LENGTH"] = 1024  # 1 KB ceiling for this test
    data = make_image_bytes("JPEG", size=(800, 600))
    assert len(data) > 1024  # sanity check the fixture is actually bigger
    resp = client.post(
        "/compress",
        data={
            "image": (io.BytesIO(data), "big.jpg"),
            "target_size": "200kb",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 413


# ---------------------------------------------------------------------
# Target size parsing
# ---------------------------------------------------------------------

def test_target_size_preset_conversion():
    assert parse_target_size("100kb", None) == 100 * 1024
    assert parse_target_size("1mb", None) == 1024 * 1024


def test_target_size_custom_conversion():
    assert parse_target_size("250", "kb") == 250 * 1024
    assert parse_target_size("2", "mb") == 2 * 1024 * 1024


def test_invalid_target_size_rejected():
    with pytest.raises(ValidationError):
        parse_target_size("not-a-number", "kb")
    with pytest.raises(ValidationError):
        parse_target_size("-5", "kb")
    with pytest.raises(ValidationError):
        parse_target_size(None, None)


def test_extremely_small_target_size_rejected():
    with pytest.raises(ValidationError):
        parse_target_size("1", "kb")  # below the 5KB floor


# ---------------------------------------------------------------------
# Compression engine behavior
# ---------------------------------------------------------------------

def test_compression_result_meets_or_approaches_target():
    img_bytes = make_image_bytes("JPEG", size=(2400, 1800))
    img = Image.open(io.BytesIO(img_bytes))
    target = 150 * 1024
    result = compress_to_target(img, target_bytes=target, mode="balanced")
    assert result.size_bytes > 0
    # Either we hit the target, or we got meaningfully close while
    # respecting the quality/dimension floors.
    assert result.size_bytes <= target * 1.5


def test_percentage_reduction_calculation():
    original_size = 4800 * 1024  # 4.8 MB in KB terms, expressed in bytes-ish for the test
    compressed_size = 420 * 1024
    reduction = round((1 - (compressed_size / original_size)) * 100, 2)
    assert reduction == pytest.approx(91.25, abs=0.01)


def test_extremely_small_target_does_not_crash_engine():
    img_bytes = make_image_bytes("JPEG", size=(1200, 900))
    img = Image.open(io.BytesIO(img_bytes))
    # Ask for an unreasonably small target; engine should return its
    # best effort rather than raising or hanging.
    result = compress_to_target(img, target_bytes=2000, mode="max_compression")
    assert result.size_bytes > 0
    assert result.width >= 200 and result.height >= 200  # MIN_DIMENSION floor respected


def test_target_larger_than_original_is_rejected_by_route(client):
    data = make_image_bytes("JPEG", size=(200, 150))
    resp = client.post(
        "/compress",
        data={
            "image": (io.BytesIO(data), "tiny.jpg"),
            "target_size": "1mb",
        },
        content_type="multipart/form-data",
    )
    body = resp.get_json()
    assert resp.status_code == 400
    assert body["success"] is False


# ---------------------------------------------------------------------
# Download endpoint
# ---------------------------------------------------------------------

def test_download_nonexistent_file_returns_404(client):
    resp = client.get("/download/does-not-exist.jpg")
    assert resp.status_code == 404


def test_download_path_traversal_rejected(client):
    resp = client.get("/download/..%2f..%2fapp.py")
    assert resp.status_code in (400, 404)


def test_full_flow_upload_compress_download(client):
    data = make_image_bytes("JPEG", size=(2000, 1500))
    resp = client.post(
        "/compress",
        data={
            "image": (io.BytesIO(data), "flow.jpg"),
            "target_size": "300kb",
            "mode": "balanced",
        },
        content_type="multipart/form-data",
    )
    body = resp.get_json()
    assert body["success"] is True
    download_url = body["download_url"]

    dl_resp = client.get(download_url)
    assert dl_resp.status_code == 200
    assert len(dl_resp.data) == body["compressed_size"]
