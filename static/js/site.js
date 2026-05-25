/** Highlight active nav link; close mobile menu after navigation */
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
})();
