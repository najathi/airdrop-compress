// AirDrop Compress website - small progressive enhancements (the page works without JS).
(() => {
  "use strict";

  // Copy buttons: next to a <code> (data-copy) or with explicit text (data-copy-text).
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-copy], [data-copy-text]");
    if (!btn) return;
    const text = btn.dataset.copyText ?? btn.parentElement.querySelector("code")?.textContent ?? "";
    try {
      await navigator.clipboard.writeText(text);
      const label = btn.textContent;
      btn.textContent = "Copied";
      setTimeout(() => (btn.textContent = label), 1500);
    } catch {
      /* clipboard unavailable (e.g. non-HTTPS preview): leave the text selectable */
    }
  });

  // Close the mobile menu after choosing a link.
  const menu = document.querySelector(".menu");
  if (menu) {
    menu.addEventListener("click", (e) => { if (e.target.closest("a")) menu.removeAttribute("open"); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") menu.removeAttribute("open"); });
  }
})();
