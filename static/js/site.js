/** Nav active state, PWA install prompt, service worker */
(function () {
  const path = window.location.pathname;
  const navLinks = document.getElementById("navLinks");
  const navToggle = document.getElementById("navToggle");

  document.querySelectorAll(".nav-links a").forEach((a) => {
    const href = a.getAttribute("href");
    if (!href) return;
    const active =
      href === path ||
      (href !== "/" && path === href) ||
      (href !== "/" && path.startsWith(href + "/"));
    if (active) a.classList.add("nav-active");

    a.addEventListener("click", () => {
      if (navLinks) navLinks.classList.remove("open");
      if (navToggle) {
        navToggle.classList.remove("active");
        navToggle.setAttribute("aria-expanded", "false");
      }
    });
  });

  // ---- PWA service worker ----
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
    });
  }

  // ---- Install banner (Android/Chrome beforeinstallprompt) ----
  const banner = document.getElementById("installBanner");
  const installBtn = document.getElementById("installAppBtn");
  const dismissBtn = document.getElementById("installDismissBtn");
  const DISMISS_KEY = "wt_install_dismissed_v1";
  let deferredPrompt = null;

  function isStandalone() {
    return (
      window.matchMedia("(display-mode: standalone)").matches ||
      window.navigator.standalone === true
    );
  }

  function showIosHint() {
    if (!banner || isStandalone()) return;
    const ua = window.navigator.userAgent || "";
    const isIOS = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    if (!isIOS) return;
    if (localStorage.getItem(DISMISS_KEY)) return;
    const copy = banner.querySelector(".install-banner-copy span");
    if (copy) {
      copy.textContent = "On iPhone: tap Share, then “Add to Home Screen” to install.";
    }
    if (installBtn) installBtn.classList.add("hidden");
    banner.classList.remove("hidden");
  }

  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredPrompt = e;
    if (localStorage.getItem(DISMISS_KEY) || isStandalone()) return;
    if (banner) banner.classList.remove("hidden");
  });

  window.addEventListener("appinstalled", () => {
    deferredPrompt = null;
    if (banner) banner.classList.add("hidden");
    localStorage.setItem(DISMISS_KEY, "1");
  });

  if (installBtn) {
    installBtn.addEventListener("click", async () => {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      try {
        await deferredPrompt.userChoice;
      } catch (_) {}
      deferredPrompt = null;
      if (banner) banner.classList.add("hidden");
    });
  }

  if (dismissBtn) {
    dismissBtn.addEventListener("click", () => {
      localStorage.setItem(DISMISS_KEY, String(Date.now()));
      if (banner) banner.classList.add("hidden");
    });
  }

  // iOS has no beforeinstallprompt — show a gentle hint instead
  showIosHint();
})();
