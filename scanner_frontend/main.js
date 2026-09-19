(() => {
  "use strict";
  const root = document.getElementById("scanner");
  const preview = document.getElementById("preview");
  const placeholder = document.getElementById("placeholder");
  const placeholderText = document.getElementById("placeholder-text");
  const status = document.getElementById("status");
  const retry = document.getElementById("retry");
  const resume = document.getElementById("resume");
  const cameraChoice = document.getElementById("camera-choice");
  const cameraSelect = document.getElementById("camera");
  const video = document.getElementById("camera-video");
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d", { willReadFrequently: true });
  let cancelVideoWait;
  let stream;
  let decodeTimer;
  let starting = false;
  let running = false;
  let disposed = false;
  let found = false;
  let rendered = false;

  function send(type, data = {}) {
    window.parent.postMessage({ isStreamlitMessage: true, type, ...data }, "*");
  }
  function resizeFrame() {
    // Measure visible content, not the initially empty video or iframe viewport.
    send("streamlit:setFrameHeight", { height: Math.ceil(root.getBoundingClientRect().height) + 2 });
  }
  function stopTracks() {
    if (stream) stream.getTracks().forEach(track => track.stop());
    stream = null;
    video.pause();
    video.srcObject = null;
  }
  async function stopCamera() {
    running = false;
    clearTimeout(decodeTimer);
    resume.hidden = true;
    if (cancelVideoWait) cancelVideoWait();
    stopTracks();
  }
  function cameraError(error) {
    const message = `${error?.name || ""} ${error?.message || error || ""}`;
    if (/NotAllowed|Permission|denied/i.test(message)) return "Camera access was denied. Allow camera access in your browser, then try again.";
    if (/NotFound|DevicesNotFound/i.test(message)) return "No camera was found. Connect a camera or find your record in Library.";
    if (/NotReadable|TrackStart|Could not start/i.test(message)) return "The camera could not start. Close other apps using it, then try again.";
    return "The camera could not open. Check camera access, then try again or use Library to find your record.";
  }
  function waitForVideo(video) {
    if (!video) throw new Error("NoPreview");
    video.muted = true;
    video.playsInline = true;
    video.setAttribute("playsinline", "");
    video.setAttribute("muted", "");
    return new Promise((resolve, reject) => {
      let settled = false;
      function cleanup() {
        clearTimeout(timer);
        video.removeEventListener("loadeddata", check);
        video.removeEventListener("playing", check);
        video.removeEventListener("error", failed);
        cancelVideoWait = null;
      }
      function check() {
        if (settled) return;
        if (!video.paused && video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0) {
          settled = true;
          cleanup(); resolve();
        }
      }
      function failed(error) {
        if (settled) return;
        settled = true;
        cleanup();
        // Camera permission and permission to play its video are separate.
        reject(new Error(error?.name === "NotAllowedError" ? "PlaybackBlocked" : "NoPreview"));
      }
      const timer = setTimeout(() => failed(video.paused ? {name: "NotAllowedError"} : null), 10000);
      cancelVideoWait = () => failed();
      video.addEventListener("loadeddata", check);
      video.addEventListener("playing", check);
      video.addEventListener("error", failed);
      // Call play synchronously here so Show camera retains the user's activation.
      // Wait for its result as readyState alone can also describe a paused video.
      try { Promise.resolve(video.play()).then(check).catch(failed); } catch (error) { failed(error); }
    });
  }
  function previewReady() {
    placeholder.hidden = true;
    resume.hidden = true;
    status.textContent = "Place the QR inside the square and hold it steady.";
    scanFrame();
  }
  function scanFrame() {
    clearTimeout(decodeTimer);
    if (!running || disposed || found) return;
    if (!video.paused && video.readyState >= 2 && video.videoWidth && video.videoHeight) {
      try {
        // Match the centre guide in the square, object-fit: cover preview.
        const side = Math.min(video.videoWidth, video.videoHeight) * 0.68;
        const size = Math.max(1, Math.min(640, Math.floor(side)));
        if (canvas.width !== size) canvas.width = canvas.height = size;
        context.drawImage(video, (video.videoWidth - side) / 2, (video.videoHeight - side) / 2,
          side, side, 0, 0, size, size);
        const pixels = context.getImageData(0, 0, size, size);
        const result = jsQR(pixels.data, size, size, { inversionAttempts: "attemptBoth" });
        if (result && result.data) { onDecoded(result.data); return; }
      } catch (_) {
        previewFailed(new Error("DecoderUnavailable"));
        return;
      }
    }
    decodeTimer = setTimeout(scanFrame, 100);
  }
  async function previewFailed(error) {
    if (disposed || found) return;
    if (/PlaybackBlocked/.test(String(error)) && running) {
      // Keep the stream attached: restarting it would lose the click activation.
      placeholder.hidden = false;
      placeholderText.textContent = "Camera preview paused";
      status.textContent = "Click Show camera to play the preview. If it stays paused in Brave, allow Autoplay for this site in Site settings, then try again.";
      resume.hidden = false;
      retry.hidden = true;
      return;
    }
    await stopCamera();
    if (disposed || found) return;
    placeholder.hidden = false;
    placeholderText.textContent = "Camera unavailable";
    status.textContent = /HTTPS/.test(String(error)) ? "Camera access needs HTTPS or localhost. Use Library to find your record."
      : /DecoderUnavailable/.test(String(error)) ? "The QR reader could not start. Reload the page or use Library to find your record."
      : /NoPreview/.test(String(error)) ? "The camera opened but no video arrived. Try another camera or check its privacy cover."
      : cameraError(error);
    retry.textContent = "Try again";
    retry.hidden = false;
  }
  async function listCameras() {
    // Enumerate after permission so browsers can provide labels and device IDs.
    // A working default camera remains usable if enumeration is unsupported.
    let devices;
    try { devices = await navigator.mediaDevices.enumerateDevices(); } catch (_) { return; }
    if (disposed || !running) return;
    const cameras = devices.filter(device => device.kind === "videoinput" && device.deviceId);
    if (!cameras.length) return;
    const currentId = stream.getVideoTracks()[0]?.getSettings().deviceId;
    const selected = currentId || cameraSelect.value || cameras[0].deviceId;
    cameraSelect.replaceChildren();
    cameras.forEach((camera, index) => {
      const option = document.createElement("option");
      option.value = camera.deviceId;
      option.textContent = camera.label || `Camera ${index + 1}`;
      cameraSelect.appendChild(option);
    });
    cameraSelect.value = selected;
    cameraChoice.hidden = false;
  }
  async function onDecoded(text) {
    if (found || disposed) return;
    found = true;
    status.textContent = "QR detected. Checking the record…";
    await stopCamera();
    if (disposed) return;
    placeholder.hidden = false;
    placeholderText.textContent = "QR detected";
    retry.textContent = "Scan again";
    retry.hidden = false;
    resizeFrame();
    send("streamlit:setComponentValue", { value: text, dataType: "json" });
  }
  async function startCamera() {
    if (starting || running || disposed) return;
    starting = true;
    cameraSelect.disabled = true;
    found = false;
    retry.hidden = true;
    resume.hidden = true;
    placeholder.hidden = false;
    placeholderText.textContent = "Starting camera…";
    status.textContent = "Allow camera access when your browser asks.";
    resizeFrame();
    try {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
        throw new Error("Camera requires HTTPS or localhost.");
      }
      if (typeof jsQR !== "function" || !context) throw new Error("DecoderUnavailable");
      const mobile = /Android|iPhone|iPad/i.test(navigator.userAgent || "");
      const constraints = cameraSelect.value
        ? { deviceId: { exact: cameraSelect.value } }
        : { facingMode: { ideal: mobile ? "environment" : "user" } };
      const acquired = await navigator.mediaDevices.getUserMedia({ video: constraints, audio: false });
      if (disposed) { acquired.getTracks().forEach(track => track.stop()); return; }
      stream = acquired;
      video.srcObject = stream;
      running = true;
      stream.getVideoTracks().forEach(track => track.addEventListener("ended", () => {
        if (running && !disposed && !found) previewFailed(new Error("NotReadableError"));
      }));
      await listCameras();
      if (disposed || found) { await stopCamera(); return; }
      status.textContent = "Waiting for the camera preview…";
      await waitForVideo(video);
      if (disposed || found) { await stopCamera(); return; }
      previewReady();
    } catch (error) {
      await previewFailed(error);
    } finally {
      starting = false;
      cameraSelect.disabled = false;
      resizeFrame();
    }
  }
  resume.addEventListener("click", async () => {
    if (starting || disposed || found || !running) return;
    starting = true;
    resume.disabled = true;
    cameraSelect.disabled = true;
    status.textContent = "Starting camera preview…";
    try {
      await waitForVideo(video);
      if (!disposed && !found) previewReady();
    } catch (error) {
      await previewFailed(error);
    } finally {
      starting = false;
      resume.disabled = false;
      cameraSelect.disabled = false;
      resizeFrame();
    }
  });
  cameraSelect.addEventListener("change", async () => {
    if (starting || disposed) return;
    cameraSelect.disabled = true;
    await stopCamera();
    send("streamlit:setComponentValue", { value: null, dataType: "json" });
    startCamera();
  });
  retry.addEventListener("click", () => {
    send("streamlit:setComponentValue", { value: null, dataType: "json" });
    startCamera();
  });
  window.addEventListener("message", event => {
    if (event.source !== window.parent || event.data?.type !== "streamlit:render") return;
    const theme = event.data.theme;
    if (theme) document.body.style.color = theme.textColor || "#31333f";
    resizeFrame();
    if (!rendered) { rendered = true; startCamera(); }
  });
  window.addEventListener("pagehide", () => {
    disposed = true;
    stopCamera();
  });
  new ResizeObserver(resizeFrame).observe(root);
  // The preview itself reserves a square before camera permission/loading completes.
  new ResizeObserver(resizeFrame).observe(preview);
  send("streamlit:componentReady", { apiVersion: 1 });
  resizeFrame();
})();
