"""Optional local webcam capture helper using OpenCV."""

import cv2


def capture_frame(camera_index=0):
    """Capture one frame from a locally connected camera as JPEG bytes.

    Browser webcam capture is used by the dashboard. This helper is available
    for scripts that need to capture from a camera connected to the server.
    """
    camera = cv2.VideoCapture(camera_index)
    if not camera.isOpened():
        camera.release()
        raise RuntimeError("Could not open the local webcam.")
    try:
        success, frame = camera.read()
        if not success or frame is None:
            raise RuntimeError("The webcam opened, but no frame could be captured.")
        encoded, jpeg = cv2.imencode(".jpg", frame)
        if not encoded:
            raise RuntimeError("OpenCV could not encode the captured frame.")
        return jpeg.tobytes()
    finally:
        camera.release()
