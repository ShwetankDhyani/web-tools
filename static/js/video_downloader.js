(() => {
  const $ = (sel) => document.querySelector(sel);

  const urlInput = $("#videoUrl");
  const fetchBtn = $("#fetchInfoBtn");
  const loadingSec = $("#loadingSection");
  const infoPanel = $("#videoInfo");
  const thumbImg = $("#videoThumb");
  const titleEl = $("#videoTitle");
  const durationEl = $("#videoDuration");
  const qualitySelect = $("#qualitySelect");
  const downloadBtn = $("#downloadBtn");
  const progressSec = $("#progressSection");
  const progressBar = $("#progressBar");
  const progressWrap = $("#progressBarWrap");
  const progressText = $("#progressText");
  const doneSec = $("#doneSection");
  const downloadLink = $("#downloadLink");
  const errorSec = $("#errorSection");
  const errorText = $("#errorText");

  function hideAll() {
    if (loadingSec) loadingSec.classList.add("hidden");
    infoPanel.classList.add("hidden");
    progressSec.classList.add("hidden");
    doneSec.classList.add("hidden");
    errorSec.classList.add("hidden");
  }

  function showError(msg) {
    hideAll();
    errorText.textContent = msg;
    errorSec.classList.remove("hidden");
  }

  function fmtDuration(s) {
    if (!s) return "";
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, "0")}`;
  }

  function setProgress(pct, label) {
    const value = Math.max(0, Math.min(100, Number(pct) || 0));
    progressBar.style.width = value + "%";
    if (progressWrap) progressWrap.setAttribute("aria-valuenow", String(Math.round(value)));
    progressText.textContent = label || `${Math.round(value)}%`;
  }

  fetchBtn.addEventListener("click", async () => {
    const url = urlInput.value.trim();
    if (!url) {
      showError("Paste a video URL first.");
      urlInput.focus();
      return;
    }

    hideAll();
    if (loadingSec) loadingSec.classList.remove("hidden");
    fetchBtn.disabled = true;
    fetchBtn.textContent = "Fetching…";

    try {
      const res = await fetch("/api/video/info", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const data = await res.json();

      if (!res.ok) {
        showError(data.error || "Could not fetch this video.");
        return;
      }

      hideAll();
      titleEl.textContent = data.title;
      thumbImg.src = data.thumbnail || "";
      thumbImg.alt = data.title ? `Thumbnail for ${data.title}` : "Video thumbnail";
      thumbImg.style.display = data.thumbnail ? "block" : "none";
      durationEl.textContent = data.duration ? `Duration: ${fmtDuration(data.duration)}` : "";

      qualitySelect.innerHTML = '<option value="best">Best available</option>';
      (data.qualities || []).forEach((q) => {
        const opt = document.createElement("option");
        opt.value = q;
        opt.textContent = `${q}p`;
        qualitySelect.appendChild(opt);
      });

      infoPanel.classList.remove("hidden");
    } catch {
      showError("Network error. Please try again.");
    } finally {
      fetchBtn.disabled = false;
      fetchBtn.textContent = "Fetch video";
    }
  });

  downloadBtn.addEventListener("click", async () => {
    const url = urlInput.value.trim();
    if (!url) return;

    downloadBtn.disabled = true;
    progressSec.classList.remove("hidden");
    doneSec.classList.add("hidden");
    errorSec.classList.add("hidden");
    setProgress(0, "Starting download…");

    try {
      const res = await fetch("/api/video/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, quality: qualitySelect.value }),
      });
      const data = await res.json();

      if (!res.ok) {
        showError(data.error || "Failed to start download.");
        downloadBtn.disabled = false;
        return;
      }

      pollProgress(data.task_id);
    } catch {
      showError("Network error.");
      downloadBtn.disabled = false;
    }
  });

  function pollProgress(taskId) {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/video/progress/${taskId}`);
        const data = await res.json();

        if (!res.ok) {
          clearInterval(interval);
          showError(data.error || "Lost track of this download.");
          downloadBtn.disabled = false;
          return;
        }

        if (data.state === "downloading") {
          setProgress(data.progress, data.status_text || `${Math.round(data.progress || 0)}%`);
        } else if (data.state === "done") {
          clearInterval(interval);
          progressSec.classList.add("hidden");
          doneSec.classList.remove("hidden");
          downloadLink.href = `/api/video/file/${taskId}`;
          downloadLink.download = data.filename || "video.mp4";
          downloadBtn.disabled = false;
        } else if (data.state === "error") {
          clearInterval(interval);
          showError(data.error || "Download failed.");
          downloadBtn.disabled = false;
        }
      } catch {
        clearInterval(interval);
        showError("Lost connection to server.");
        downloadBtn.disabled = false;
      }
    }, 1000);
  }

  urlInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") fetchBtn.click();
  });

  // Prefill from ?url= (PWA share target / deep links)
  try {
    const params = new URLSearchParams(window.location.search);
    const shared = (params.get("url") || "").trim();
    if (shared) {
      urlInput.value = shared;
      fetchBtn.click();
    }
  } catch (_) {}
})();
