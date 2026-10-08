// Shared page helpers: flash messages, KaTeX rendering, confirm-before-submit, job redirect.
(function () {
  "use strict";

  function flash(level, message) {
    const host = document.getElementById("flash");
    if (!host) return;
    const box = document.createElement("div");
    box.className = "flash flash-" + level;
    box.setAttribute("role", "status");
    const text = document.createElement("span");
    text.textContent = message;
    const close = document.createElement("button");
    close.type = "button";
    close.className = "flash-close";
    close.setAttribute("aria-label", "Tutup");
    close.textContent = "\u00d7";
    close.addEventListener("click", () => box.remove());
    box.append(text, close);
    host.replaceChildren(box);
  }

  function renderTex(root) {
    if (!window.katex || !root || !root.querySelectorAll) return;
    root.querySelectorAll("[data-tex]").forEach((el) => {
      katex.render(el.dataset.tex, el, {
        throwOnError: false,
        displayMode: el.hasAttribute("data-display"),
      });
    });
  }

  // `/api` errors are {"detail": "message"} or FastAPI's list of {loc, msg}.
  function errorText(data, fallback) {
    const detail = data && data.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((e) => ((e.loc || []).slice(1).join(".") || "input") + ": " + e.msg)
        .join("; ");
    }
    return fallback;
  }

  async function requestJson(url, options) {
    const response = await fetch(url, {
      ...options,
      headers: { "Content-Type": "application/json", Accept: "application/json" },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(errorText(data, "HTTP " + response.status));
    }
    return data;
  }

  window.mathGrader = { flash, renderTex, errorText, requestJson };

  document.addEventListener(
    "submit",
    (event) => {
      const form = event.target.closest("form[data-confirm]");
      if (form && !window.confirm(form.dataset.confirm)) event.preventDefault();
    },
    true,
  );

  document.addEventListener("DOMContentLoaded", () => renderTex(document.body));

  let redirecting = false;
  function followFinishedJob() {
    const next = document.querySelector("[data-autoredirect] [data-next]");
    if (!next || redirecting) return;
    redirecting = true;
    window.setTimeout(() => window.location.assign(next.href), 800);
  }

  document.addEventListener("htmx:afterSettle", (event) => {
    renderTex(event.target);
    followFinishedJob();
  });
  document.addEventListener("htmx:sseMessage", () => window.setTimeout(followFinishedJob, 50));
})();
