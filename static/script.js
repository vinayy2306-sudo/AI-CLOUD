/* Browser-side upload preview and webcam capture. */
(() => {
  const form = document.getElementById("upload-form");
  if (!form) return;

  const input = document.getElementById("image-input");
  const selectedFile = document.getElementById("selected-file");
  const selectedName = document.getElementById("selected-name");
  const analyzeButton = document.getElementById("analyze-button");
  const imagePreview = document.getElementById("image-preview");
  const previewEmpty = document.getElementById("preview-empty");
  const previewTag = document.getElementById("preview-tag");
  const errorMessage = document.getElementById("error-message");
  const dropzone = document.getElementById("dropzone");
  const video = document.getElementById("camera-video");
  const cameraStage = document.getElementById("camera-stage");
  const cameraStart = document.getElementById("camera-start");
  const cameraCapture = document.getElementById("camera-capture");
  let cameraStream = null;
  let previewUrl = null;

  function showError(message) {
    errorMessage.textContent = message;
    errorMessage.hidden = false;
  }

  function clearError() {
    errorMessage.textContent = "";
    errorMessage.hidden = true;
  }

  function setImage(file) {
    if (!file) return;
    const extension = file.name.split(".").pop().toLowerCase();
    if (!["jpg", "jpeg", "png"].includes(extension) ||
        (file.type && !["image/jpeg", "image/png"].includes(file.type))) {
      showError("Unsupported image. Choose a JPG, JPEG, or PNG file.");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      showError("Image is too large. The maximum file size is 5 MB.");
      return;
    }
    clearError();
    input.files = createFileList(file);
    selectedFile.hidden = false;
    selectedName.textContent = file.name;
    analyzeButton.disabled = false;
    previewEmpty.hidden = true;
    imagePreview.hidden = false;
    previewTag.textContent = "IMAGE SELECTED";
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(file);
    imagePreview.src = previewUrl;
  }

  function createFileList(file) {
    const transfer = new DataTransfer();
    transfer.items.add(file);
    return transfer.files;
  }

  input.addEventListener("change", () => setImage(input.files[0]));
  document.getElementById("remove-file").addEventListener("click", () => {
    input.value = "";
    selectedFile.hidden = true;
    analyzeButton.disabled = true;
    imagePreview.hidden = true;
    imagePreview.removeAttribute("src");
    previewEmpty.hidden = false;
    previewTag.textContent = "NO IMAGE";
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
    clearError();
  });

  ["dragenter", "dragover"].forEach((name) => {
    dropzone.addEventListener(name, (event) => {
      event.preventDefault();
      dropzone.classList.add("drag-over");
    });
  });
  ["dragleave", "drop"].forEach((name) => {
    dropzone.addEventListener(name, (event) => {
      event.preventDefault();
      dropzone.classList.remove("drag-over");
    });
  });
  dropzone.addEventListener("drop", (event) => {
    const file = event.dataTransfer.files[0];
    if (file) setImage(file);
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = input.files[0];
    if (!file) return;
    clearError();
    analyzeButton.disabled = true;
    analyzeButton.querySelector("span").textContent = "Analyzing…";
    const body = new FormData();
    body.append("image", file, file.name);
    try {
      const response = await fetch("/api/detect", { method: "POST", body });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Detection failed. Please try again.");
      window.location.assign(`/results/${encodeURIComponent(result.id)}`);
    } catch (error) {
      showError(error.message || "Could not reach the server. Check your connection and try again.");
      analyzeButton.disabled = false;
      analyzeButton.querySelector("span").textContent = "Analyze image";
    }
  });

  cameraStart.addEventListener("click", async () => {
    clearError();
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      showError("Camera access is not available in this browser. Use localhost or a secure HTTPS page.");
      return;
    }
    try {
      cameraStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
      video.srcObject = cameraStream;
      cameraStage.hidden = false;
      cameraCapture.disabled = false;
      cameraStart.textContent = "Camera is open";
      cameraStart.disabled = true;
    } catch (error) {
      const permissionError = error.name === "NotAllowedError" || error.name === "SecurityError";
      showError(permissionError
        ? "Camera permission was denied. Allow camera access in your browser settings, or upload an image instead."
        : "The camera could not be opened. Check that it is connected and not being used by another app.");
    }
  });

  cameraCapture.addEventListener("click", () => {
    if (!video.videoWidth || !video.videoHeight) {
      showError("The camera is still starting. Wait a moment and try again.");
      return;
    }
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) {
        showError("The browser could not capture an image from the camera.");
        return;
      }
      setImage(new File([blob], `webcam-${Date.now()}.jpg`, { type: "image/jpeg" }));
    }, "image/jpeg", 0.92);
  });

  window.addEventListener("beforeunload", () => {
    if (cameraStream) cameraStream.getTracks().forEach((track) => track.stop());
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  });
})();
