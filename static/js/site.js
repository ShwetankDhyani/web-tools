/** Highlight active nav link from current path */
(function () {
  const path = window.location.pathname;
  document.querySelectorAll(".nav-links a").forEach((a) => {
    const href = a.getAttribute("href");
    if (!href) return;
    const active =
      href === path ||
      (href !== "/" && path === href) ||
      (href !== "/" && path.startsWith(href + "/"));
    if (active) a.classList.add("nav-active");
  });
})();
