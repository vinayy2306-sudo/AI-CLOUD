"""Flask web application for the object-detection dashboard."""

import io
import os
import threading
import uuid
import warnings
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory, url_for
from PIL import Image, UnidentifiedImageError
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
from dotenv import load_dotenv

load_dotenv(BASE_DIR / ".env", override=False)

from aws_services import (  # noqa: E402
    AWSServiceError,
    AwsConfigurationError,
    detect_labels,
    ensure_s3_bucket_configured,
    save_to_s3,
)

UPLOAD_FOLDER = BASE_DIR / "uploads"
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
HISTORY_LIMIT = 10
DEMO_MODE_VALUE = os.getenv("DEMO_MODE", "true").strip().lower()
if DEMO_MODE_VALUE not in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
    raise RuntimeError("DEMO_MODE must be true or false.")
DEMO_MODE = DEMO_MODE_VALUE in {"1", "true", "yes", "on"}

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

app = Flask(__name__)
app.config.update(
    MAX_CONTENT_LENGTH=MAX_IMAGE_BYTES + 64 * 1024,
    UPLOAD_FOLDER=str(UPLOAD_FOLDER),
)
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

_history = []
_history_lock = threading.Lock()


def _image_extension(filename):
    """Return a permitted extension, or None for an unsupported filename."""
    safe_name = secure_filename(filename or "")
    if "." not in safe_name:
        return None
    extension = safe_name.rsplit(".", 1)[1].lower()
    return extension if extension in ALLOWED_EXTENSIONS else None


def _validate_image(image_bytes, extension):
    """Check that bytes contain a decodable image matching its file extension."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(image_bytes)) as image:
                expected_format = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG"}[extension]
                if image.format != expected_format:
                    raise ValueError("The image contents do not match the file extension.")
                image.verify()
            with Image.open(io.BytesIO(image_bytes)) as image:
                image.load()
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("The file is not a valid, safely decodable image.") from exc


def _remember_detection(detection):
    """Keep only a small recent history and remove expired local image copies."""
    with _history_lock:
        _history.insert(0, detection)
        expired = _history[HISTORY_LIMIT:]
        del _history[HISTORY_LIMIT:]
    for old_detection in expired:
        try:
            Path(old_detection["local_path"]).unlink(missing_ok=True)
        except OSError:
            app.logger.warning("Could not remove expired local upload %s", old_detection["id"])


def _object_total(labels):
    return sum(max(1, int(label.get("instances_count", 0))) for label in labels)


@app.context_processor
def inject_dashboard_state():
    with _history_lock:
        recent = [
            {key: value for key, value in item.items() if key != "local_path"}
            for item in _history[:5]
        ]
    return {"demo_mode": DEMO_MODE, "recent_detections": recent}


@app.get("/")
def index():
    with _history_lock:
        detections = list(_history)
    object_total = sum(_object_total(item["labels"]) for item in detections)
    return render_template(
        "index.html",
        detection_count=len(detections),
        object_total=object_total,
    )


@app.post("/api/detect")
def api_detect():
    uploaded_file = request.files.get("image")
    if uploaded_file is None or not uploaded_file.filename:
        return jsonify(error="Choose an image file before submitting."), 400

    extension = _image_extension(uploaded_file.filename)
    if extension is None:
        return jsonify(error="Unsupported file type. Upload a JPG, JPEG, or PNG image."), 400

    image_bytes = uploaded_file.read(MAX_IMAGE_BYTES + 1)
    if not image_bytes:
        return jsonify(error="The selected image is empty."), 400
    if len(image_bytes) > MAX_IMAGE_BYTES:
        return jsonify(error="Image is too large. The maximum file size is 5 MB."), 413

    try:
        _validate_image(image_bytes, extension)
        if DEMO_MODE:
            labels = [
                {"name": "Person", "confidence": 98.4, "instances_count": 1},
                {"name": "Chair", "confidence": 94.7, "instances_count": 2},
                {"name": "Bottle", "confidence": 91.2, "instances_count": 1},
            ]
        else:
            ensure_s3_bucket_configured()
            labels = detect_labels(image_bytes)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except AwsConfigurationError as exc:
        return jsonify(error=str(exc)), 503
    except AWSServiceError as exc:
        app.logger.exception("AWS object detection or storage failed")
        return jsonify(error=str(exc)), 502

    detection_id = uuid.uuid4().hex
    safe_name = secure_filename(uploaded_file.filename) or "capture"
    local_filename = detection_id + "." + extension
    local_path = UPLOAD_FOLDER / local_filename
    local_path.write_bytes(image_bytes)

    detected_at = datetime.now(timezone.utc).isoformat()
    report = {
        "id": detection_id,
        "original_filename": safe_name,
        "detected_at": detected_at,
        "mode": "demo" if DEMO_MODE else "aws",
        "labels": labels,
        "object_count": _object_total(labels),
    }

    if not DEMO_MODE:
        try:
            report["s3"] = save_to_s3(image_bytes, report, extension)
        except (AwsConfigurationError, AWSServiceError) as exc:
            local_path.unlink(missing_ok=True)
            app.logger.exception("Could not store detection in S3")
            return jsonify(error=str(exc)), 503 if isinstance(exc, AwsConfigurationError) else 502

    detection = {
        **report,
        "image_url": url_for("uploaded_image", detection_id=detection_id),
        "local_path": str(local_path),
    }
    _remember_detection(detection)
    return jsonify(
        {
            key: value
            for key, value in detection.items()
            if key != "local_path"
        }
    )


@app.errorhandler(RequestEntityTooLarge)
def request_too_large(_error):
    return jsonify(error="Image is too large. The maximum file size is 5 MB."), 413


@app.get("/results/<detection_id>")
def results(detection_id):
    with _history_lock:
        detection = next((item for item in _history if item["id"] == detection_id), None)
    if detection is None:
        return render_template("results.html", detection=None), 404
    return render_template("results.html", detection=detection)


@app.get("/uploads/<detection_id>")
def uploaded_image(detection_id):
    with _history_lock:
        detection = next((item for item in _history if item["id"] == detection_id), None)
    if detection is None:
        return "Image not found.", 404
    return send_from_directory(UPLOAD_FOLDER, Path(detection["local_path"]).name)


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
