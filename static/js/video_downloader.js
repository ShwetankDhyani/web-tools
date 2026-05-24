(() => {
  const $ = (sel) => document.querySelector(sel);

  const urlInput     = $("#videoUrl");
  const fetchBtn     = $("#fetchInfoBtn");
  const infoPanel    = $("#videoInfo");
  const thumbImg     = $("#videoThumb");
  const titleEl      = $("#videoTitle");
  const durationEl   = $("#videoDuration");
  const qualitySelect = $("#qualitySelect");
  const downloadBtn  = $("#downloadBtn");
  const progressSec  = $("#progressSection");
  const progressBar  = $("#progressBar");
  const progressText = $("#progressText");
  const doneSec      = $("#doneSection");
  const downloadLink = $("#downloadLink");
  const errorSec     = $("#errorSection");
  const errorText    = $("#errorText");

  function hideAll() {
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

  // ---- Fetch video info ----
  fetchBtn.addEventListener("click", async () => {
    const url = urlInput.value.trim();
    if (!url) return;

    hideAll();
    fetchBtn.disabled = true;
    fetchBtn.textContent = "Fetching...";

    try {
      const res = await fetch("/api/video/info", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const data = await res.json();

      if (!res.ok) {
        showError(data.error || "Unknown error");
        return;
      }

      titleEl.textContent = data.title;
      thumbImg.src = data.thumbnail || "";
      thumbImg.style.display = data.thumbnail ? "block" : "none";
      durationEl.textContent = data.duration ? `Duration: ${fmtDuration(data.duration)}` : "";

      // Populate quality options
      qualitySelect.innerHTML = '<option value="best">Best Available</option>';
      (data.qualities || []).forEach((q) => {
        const opt = document.createElement("option");
        opt.value = q;
        opt.textContent = `${q}p`;
        qualitySelect.appendChild(opt);
      });

      infoPanel.classList.remove("hidden");
    } catch (err) {
      showError("Network error. Please try again.");
    } finally {
      fetchBtn.disabled = false;
      fetchBtn.textContent = "Fetch Video";
    }
  });

  // ---- Start download ----
  downloadBtn.addEventListener("click", async () => {
    const url = urlInput.value.trim();
    if (!url) return;

    downloadBtn.disabled = true;
    progressSec.classList.remove("hidden");
    doneSec.classList.add("hidden");
    errorSec.classList.add("hidden");
    progressBar.style.width = "0%";
    progressText.textContent = "Starting download...";

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

  // ---- Poll progress ----
  function pollProgress(taskId) {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/video/progress/${taskId}`);
        const data = await res.json();

        if (data.state === "downloading") {
          progressBar.style.width = data.progress + "%";
          progressText.textContent = data.status_text || `${Math.round(data.progress)}%`;
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

  // Submit on Enter
  urlInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") fetchBtn.click();
  });
})();
