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
  const scanGuide = document.getElementById("scan-guide");
  let cameras = [];
  let cancelVideoWait;
  let reader;
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
    document.querySelectorAll("video").forEach(video => {
      if (video.srcObject) video.srcObject.getTracks().forEach(track => track.stop());
    });
  }
  async function stopCamera() {
    resume.hidden = true;
    if (cancelVideoWait) cancelVideoWait();
    if (reader && running) {
      try { await reader.stop(); } catch (_) { /* Also release tracks below. */ }
    }
    running = false;
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
      function cleanup() {
        clearTimeout(timer);
        video.removeEventListener("loadeddata", check);
        video.removeEventListener("playing", check);
        video.removeEventListener("error", failed);
        cancelVideoWait = null;
      }
      function check() {
        if (!video.paused && video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0) { cleanup(); resolve(); }
      }
      function failed(error) {
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
      : /NoPreview/.test(String(error)) ? "The camera opened but no video arrived. Try another camera or check its privacy cover."
      : cameraError(error);
    retry.textContent = "Try again";
    retry.hidden = false;
  }
  async function listCameras() {
    if (cameras.length) return;
    cameras = await Html5Qrcode.getCameras();
    if (!cameras.length) throw new Error("NotFoundError");
    cameraSelect.replaceChildren();
    cameras.forEach((camera, index) => {
      const option = document.createElement("option");
      option.value = camera.id;
      option.textContent = camera.label || `Camera ${index + 1}`;
      cameraSelect.appendChild(option);
    });
    const mobile = /Android|iPhone|iPad/i.test(navigator.userAgent || "");
    const preferred = mobile ? cameras.find(camera => /back|rear|environment/i.test(camera.label)) : null;
    cameraSelect.value = (preferred || cameras[0]).id;
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
      await listCameras();
      if (disposed) return;
      if (!reader) reader = new Html5Qrcode("qr-reader");
      await reader.start(
        cameraSelect.value,
        {
          fps: 10,
          qrbox: (width, height) => {
            const side = Math.max(50, Math.floor(Math.min(width, height) * 0.68));
            scanGuide.style.width = `${side}px`;
            scanGuide.style.height = `${side}px`;
            return { width: side, height: side };
          }
        },
        onDecoded,
        () => {} // A frame without a QR is normal while positioning it.
      );
      running = true;
      if (disposed || found) { await stopCamera(); return; }
      status.textContent = "Waiting for the camera preview…";
      await waitForVideo(document.querySelector("#qr-reader video"));
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
      await waitForVideo(document.querySelector("#qr-reader video"));
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
    stopTracks();
    stopCamera();
  });
  new ResizeObserver(resizeFrame).observe(root);
  // The preview itself reserves a square before camera permission/loading completes.
  new ResizeObserver(resizeFrame).observe(preview);
  send("streamlit:componentReady", { apiVersion: 1 });
  resizeFrame();
})();
