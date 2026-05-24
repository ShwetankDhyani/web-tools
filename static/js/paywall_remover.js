(() => {
  const $ = (sel) => document.querySelector(sel);

  const urlInput    = $("#articleUrl");
  const readBtn     = $("#readBtn");
  const loadingSec  = $("#loadingSection");
  const articleSec  = $("#articleSection");
  const articleTitle   = $("#articleTitle");
  const articleSource  = $("#articleSource");
  const articleContent = $("#articleContent");
  const errorSec  = $("#errorSection");
  const errorText = $("#errorText");

  function hideAll() {
    loadingSec.classList.add("hidden");
    articleSec.classList.add("hidden");
    errorSec.classList.add("hidden");
  }

  function showError(msg) {
    hideAll();
    errorText.textContent = msg;
    errorSec.classList.remove("hidden");
  }

  readBtn.addEventListener("click", async () => {
    const url = urlInput.value.trim();
    if (!url) return;

    hideAll();
    loadingSec.classList.remove("hidden");
    readBtn.disabled = true;
    readBtn.textContent = "Reading...";

    try {
      const res = await fetch("/api/paywall/read", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const data = await res.json();

      if (!res.ok) {
        showError(data.error || "Could not fetch article.");
        return;
      }

      articleTitle.textContent = data.title || "Untitled";
      articleSource.href = data.source_url;
      articleContent.innerHTML = data.content;
      hideAll();
      articleSec.classList.remove("hidden");
    } catch {
      showError("Network error. Please try again.");
    } finally {
      readBtn.disabled = false;
      readBtn.textContent = "Read Article";
    }
  });

  urlInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") readBtn.click();
  });
})();
