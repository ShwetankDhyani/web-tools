(() => {
  const $ = (sel) => document.querySelector(sel);

  const urlInput       = $("#articleUrl");
  const readBtn        = $("#readBtn");
  const loadingSec     = $("#loadingSection");
  const articleSec     = $("#articleSection");
  const articleTitle   = $("#articleTitle");
  const articleSource  = $("#articleSource");
  const siteFavicon    = $("#siteFavicon");
  const siteName       = $("#siteName");
  const styledFrame    = $("#styledFrame");
  const errorSec       = $("#errorSection");
  const errorText      = $("#errorText");

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

  function buildStyledDocument(data) {
    const styles = data.site_styles || {};
    const stylesheetLinks = (styles.stylesheets || [])
      .map((href) => `<link rel="stylesheet" href="${href}" crossorigin="anonymous">`)
      .join("\n");
    const inlineStyles = (styles.inline_styles || [])
      .map((css) => `<style>${css}</style>`)
      .join("\n");

    return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <base href="${styles.base_url || ""}/" target="_blank">
  ${stylesheetLinks}
  ${inlineStyles}
  <style>
    /* Reader-level overrides to keep it clean */
    body {
      margin: 0 auto;
      padding: 2rem 1.5rem;
      max-width: 780px;
      overflow-x: hidden;
    }
    img, video, picture {
      max-width: 100%;
      height: auto;
    }
    figure { margin: 1.5em 0; }
    table { max-width: 100%; overflow-x: auto; display: block; }
    nav, header, footer, aside,
    [class*="sidebar"], [class*="nav-"],
    [class*="header-"], [class*="footer-"],
    [class*="social"], [class*="share"],
    [class*="related"], [class*="recommend"],
    [class*="comment"], [class*="newsletter"],
    [class*="popup"], [class*="modal"],
    [class*="banner"], [class*="promo"],
    [class*="advert"], [class*="sponsor"],
    [id*="cookie"], [id*="consent"] {
      display: none !important;
    }
  </style>
</head>
<body>
  ${data.content}
</body>
</html>`;
  }

  function renderArticle(data) {
    hideAll();

    // Site bar
    const styles = data.site_styles || {};
    if (styles.favicon) {
      siteFavicon.src = styles.favicon;
      siteFavicon.style.display = "";
    } else {
      siteFavicon.style.display = "none";
    }
    siteName.textContent = styles.site_name || new URL(data.source_url).hostname;
    articleSource.href = data.source_url;
    articleTitle.textContent = data.title || "Untitled";

    // Write styled content into iframe
    const doc = styledFrame.contentDocument || styledFrame.contentWindow.document;
    doc.open();
    doc.write(buildStyledDocument(data));
    doc.close();

    // Auto-resize iframe to content height
    const resizeFrame = () => {
      try {
        const h = doc.documentElement.scrollHeight;
        if (h > 100) styledFrame.style.height = h + 40 + "px";
      } catch {}
    };
    // Resize after styles load
    setTimeout(resizeFrame, 500);
    setTimeout(resizeFrame, 1500);
    setTimeout(resizeFrame, 3000);
    // Also resize when images load
    const images = doc.querySelectorAll("img");
    images.forEach((img) => img.addEventListener("load", resizeFrame));

    articleSec.classList.remove("hidden");
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

      renderArticle(data);
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
