// Shared page helpers: toasts, KaTeX rendering, confirm-before-submit, busy buttons, job redirect.
(function () {
  "use strict";

  const FLASH_ICONS = { ok: "circle-check", warn: "triangle-alert", error: "circle-x" };
  const AUTO_DISMISS_MS = 5000;

  function icon(name) {
    const sprite = document.querySelector(".brand use");
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "icon");
    svg.setAttribute("aria-hidden", "true");
    if (sprite) {
      const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
      use.setAttribute("href", sprite.getAttribute("href").split("#")[0] + "#" + name);
      svg.append(use);
    }
    return svg;
  }

  function flash(level, message) {
    const host = document.getElementById("flash");
    if (!host) return;
    const box = document.createElement("div");
    box.className = "flash flash-" + level;
    box.setAttribute("role", "status");
    const body = document.createElement("span");
    body.className = "flash-body";
    const text = document.createElement("span");
    text.textContent = message;
    body.append(icon(FLASH_ICONS[level] || "info"), text);
    const close = document.createElement("button");
    close.type = "button";
    close.className = "flash-close";
    close.setAttribute("aria-label", "Tutup");
    close.textContent = "\u00d7";
    close.addEventListener("click", () => box.remove());
    box.append(body, close);
    host.replaceChildren(box);
    if (level === "ok") window.setTimeout(() => box.remove(), AUTO_DISMISS_MS);
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

  // Plain POSTs start jobs and redirect; HTMX forms already get `.htmx-request`.
  document.addEventListener("submit", (event) => {
    if (event.defaultPrevented) return;
    const button = event.submitter || event.target.querySelector("button:not([type=button])");
    if (button) button.classList.add("is-busy");
  });
  window.addEventListener("pageshow", () => {
    document.querySelectorAll(".is-busy").forEach((el) => el.classList.remove("is-busy"));
  });

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
