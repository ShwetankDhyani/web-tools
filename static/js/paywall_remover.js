(() => {
  const $ = (sel) => document.querySelector(sel);

  const urlInput       = $("#articleUrl");
  const readBtn        = $("#readBtn");
  const loadingSec     = $("#loadingSection");
  const articleSec     = $("#articleSection");
  const articleTitle   = $("#articleTitle");
  const articleSource  = $("#articleSource");
  const articleContent = $("#articleContent");
  const originalSec    = $("#originalSection");
  const originalFrame  = $("#originalFrame");
  const viewToggle     = $("#viewToggle");
  const btnOriginal    = $("#btnOriginal");
  const btnReader      = $("#btnReader");
  const errorSec       = $("#errorSection");
  const errorText      = $("#errorText");

  let cachedData = { reader: null, original: null };
  let currentMode = "original";
  let currentUrl = "";

  function hideAll() {
    loadingSec.classList.add("hidden");
    articleSec.classList.add("hidden");
    originalSec.classList.add("hidden");
    errorSec.classList.add("hidden");
  }

  function showError(msg) {
    hideAll();
    viewToggle.classList.add("hidden");
    errorText.textContent = msg;
    errorSec.classList.remove("hidden");
  }

  function showOriginal(data) {
    hideAll();
    const doc = originalFrame.contentDocument || originalFrame.contentWindow.document;
    doc.open();
    doc.write(data.original_html);
    doc.close();
    originalSec.classList.remove("hidden");
  }

  function showReader(data) {
    hideAll();
    articleTitle.textContent = data.title || "Untitled";
    articleContent.innerHTML = data.content;
    articleSec.classList.remove("hidden");
  }

  async function fetchMode(mode) {
    if (cachedData[mode]) {
      if (mode === "original") showOriginal(cachedData[mode]);
      else showReader(cachedData[mode]);
      return;
    }

    hideAll();
    loadingSec.classList.remove("hidden");

    try {
      const res = await fetch("/api/paywall/read", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: currentUrl, mode }),
      });
      const data = await res.json();

      if (!res.ok) {
        showError(data.error || "Could not fetch article.");
        return;
      }

      cachedData[mode] = data;
      if (data.source_url) articleSource.href = data.source_url;

      if (mode === "original") showOriginal(data);
      else showReader(data);
    } catch {
      showError("Network error. Please try again.");
    }
  }

  readBtn.addEventListener("click", async () => {
    const url = urlInput.value.trim();
    if (!url) return;

    currentUrl = url;
    cachedData = { reader: null, original: null };
    currentMode = "original";

    hideAll();
    loadingSec.classList.remove("hidden");
    readBtn.disabled = true;
    readBtn.textContent = "Reading...";

    // Update toggle state
    btnOriginal.classList.add("active");
    btnReader.classList.remove("active");

    try {
      // Fetch both modes in parallel
      const [origRes, readerRes] = await Promise.all([
        fetch("/api/paywall/read", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url, mode: "original" }),
        }),
        fetch("/api/paywall/read", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url, mode: "reader" }),
        }),
      ]);

      const origData = await origRes.json();
      const readerData = await readerRes.json();

      if (!origRes.ok && !readerRes.ok) {
        showError(origData.error || readerData.error || "Could not fetch article.");
        return;
      }

      if (origRes.ok) cachedData.original = origData;
      if (readerRes.ok) cachedData.reader = readerData;

      articleSource.href = url;
      viewToggle.classList.remove("hidden");

      // Show original view first
      if (cachedData.original) {
        showOriginal(cachedData.original);
      } else if (cachedData.reader) {
        currentMode = "reader";
        btnReader.classList.add("active");
        btnOriginal.classList.remove("active");
        showReader(cachedData.reader);
      }
    } catch {
      showError("Network error. Please try again.");
    } finally {
      readBtn.disabled = false;
      readBtn.textContent = "Read Article";
    }
  });

  // Toggle buttons
  btnOriginal.addEventListener("click", () => {
    if (currentMode === "original") return;
    currentMode = "original";
    btnOriginal.classList.add("active");
    btnReader.classList.remove("active");
    fetchMode("original");
  });

  btnReader.addEventListener("click", () => {
    if (currentMode === "reader") return;
    currentMode = "reader";
    btnReader.classList.add("active");
    btnOriginal.classList.remove("active");
    fetchMode("reader");
  });

  urlInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") readBtn.click();
  });
})();
