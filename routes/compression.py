"""
HTTP layer only. This module translates between Flask request/response
objects and the pure functions in services/ and utils/ — it should never
contain compression logic or filesystem-path assembly itself.
"""

import os
import traceback

from flask import Blueprint, jsonify, request, send_file, current_app
from werkzeug.exceptions import HTTPException
from PIL import Image

from config import OUTPUT_DIR
from services.image_compressor import CompressionError, compress_to_target
from utils.file_utils import (
    cleanup_expired_files,
    human_readable_size,
    make_safe_filename,
    safe_join,
)
from utils.validation import (
    ValidationError,
    parse_target_size,
    validate_compression_mode,
    validate_dimension,
    validate_extension,
    validate_file_size,
    validate_image_content,
    validate_output_format,
    validate_quality,
)

bp = Blueprint("compression", __name__)


@bp.route("/compress", methods=["POST"])
def compress():
    cleanup_expired_files()

    try:
        if "image" not in request.files:
            raise ValidationError("No image file was uploaded.", field="file")
        file = request.files["image"]
        if file.filename == "":
            raise ValidationError("No image file was selected.", field="file")

        validate_extension(file.filename)

        # Determine size without trusting Content-Length: read once, measure.
        file.stream.seek(0, os.SEEK_END)
        size_bytes = file.stream.tell()
        file.stream.seek(0)
        validate_file_size(size_bytes)

        detected_format = validate_image_content(file.stream)

        target_bytes = parse_target_size(
            request.form.get("target_size"), request.form.get("target_unit")
        )
        mode = validate_compression_mode(request.form.get("mode"))
        output_format = validate_output_format(request.form.get("output_format"))
        max_width = validate_dimension(request.form.get("max_width"), "Maximum width")
        max_height = validate_dimension(request.form.get("max_height"), "Maximum height")
        fixed_quality = validate_quality(request.form.get("quality"))

        if target_bytes >= size_bytes:
            raise ValidationError(
                "Target size is already larger than (or equal to) the original file. "
                "Choose a smaller target size.",
                field="target_size",
            )

        file.stream.seek(0)
        with Image.open(file.stream) as img:
            img.load()
            original_width, original_height = img.size

            result = compress_to_target(
                img,
                target_bytes=target_bytes,
                mode=mode,
                output_format=output_format,
                max_width=max_width,
                max_height=max_height,
                fixed_quality=fixed_quality,
            )

        out_filename = make_safe_filename(result.pillow_format)
        out_path = safe_join(OUTPUT_DIR, out_filename)
        with open(out_path, "wb") as f:
            f.write(result.data)

        reduction_pct = round((1 - (result.size_bytes / size_bytes)) * 100, 2) if size_bytes else 0
        target_reached = result.size_bytes <= target_bytes

        response = {
            "success": True,
            "original_filename": file.filename,
            "original_size": size_bytes,
            "original_size_readable": human_readable_size(size_bytes),
            "original_dimensions": {"width": original_width, "height": original_height},
            "compressed_size": result.size_bytes,
            "compressed_size_readable": human_readable_size(result.size_bytes),
            "new_dimensions": {"width": result.width, "height": result.height},
            "output_format": result.pillow_format,
            "quality_used": result.quality_used,
            "reduction_percent": reduction_pct,
            "target_bytes": target_bytes,
            "target_reached": target_reached,
            "download_url": f"/download/{out_filename}",
            "attempts": result.attempts,
        }
        if not target_reached:
            response["warning"] = (
                "Could not reach the exact target size without unacceptable quality loss. "
                "Showing the smallest result achieved instead."
            )
        return jsonify(response), 200

    except ValidationError as e:
        return jsonify({"success": False, "error": e.message, "field": e.field}), 400
    except CompressionError as e:
        return jsonify({"success": False, "error": e.message}), 422
    except HTTPException:
        # Let Flask's own error handling (e.g. 413 for oversized bodies)
        # take care of these instead of masking them as a generic 500.
        raise
    except Exception:
        # Never leak stack traces or internal paths to the client.
        current_app.logger.error("Unhandled error in /compress:\n%s", traceback.format_exc())
        return jsonify({"success": False, "error": "An unexpected server error occurred while processing the image."}), 500


@bp.route("/download/<filename>", methods=["GET"])
def download(filename):
    try:
        path = safe_join(OUTPUT_DIR, filename)
    except ValueError:
        return jsonify({"success": False, "error": "Invalid file reference."}), 400

    if not os.path.isfile(path):
        return jsonify({"success": False, "error": "This file has expired or does not exist. Please compress the image again."}), 404

    download_name = f"compressed_{filename}"
    return send_file(path, as_attachment=True, download_name=download_name)
