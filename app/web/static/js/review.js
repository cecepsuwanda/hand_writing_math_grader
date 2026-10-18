// Transcription review: one Alpine editor per question.json, KaTeX preview of the SymPy form.
(function () {
  "use strict";

  const PENDING = undefined; // previewTex: undefined = waiting, null = unparseable
  const FIGURE_TOKEN = /^(GRAPH_POINTS|NUMBER_LINE)\b/i;

  const hasDirtyReview = () =>
    Boolean(document.querySelector('.review-item[data-dirty="true"]'));

  window.addEventListener("beforeunload", (event) => {
    if (hasDirtyReview()) {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) {
      return;
    }
    const action = form.getAttribute("action") || "";
    if (!action.includes("/finish-questions") || !hasDirtyReview()) {
      return;
    }
    const discard = window.confirm(
      "Ada perubahan review yang belum disimpan. Simpan dulu, atau buang edit dan nilai dari file di disk?"
    );
    if (!discard) {
      event.preventDefault();
    }
  });

  document.addEventListener("alpine:init", () => {
    window.Alpine.data("questionEditor", (config) => {
      let keySeq = 0;
      const symbolic = (payload) => ({
        kind: (payload && payload.kind) || "",
        repr: (payload && payload.repr) || "",
        previewTex: PENDING,
      });
      const toStep = (step) => ({
        ...step,
        ...symbolic(step.symbolic),
        role: step.role || "",
        // Stick to the step object so renumber/move does not reattach flags by number.
        reviewFlags: (config.flags && config.flags[String(step.step_number)]) || [],
        key: ++keySeq,
      });
      const toFigure = (fig) => ({
        path: (fig && fig.path) || "",
        caption: (fig && fig.caption) || "",
        page_number: fig && fig.page_number != null ? fig.page_number : null,
        ...symbolic(fig && fig.symbolic),
        key: ++keySeq,
      });
      const toPayload = (kind, repr) => (kind ? { kind, repr: repr.trim() } : null);
      const isFigureToken = (target) =>
        (target.kind || "") === "figure" || FIGURE_TOKEN.test((target.repr || "").trim());

      return {
        original: config.question,
        steps: config.question.student_steps.map(toStep),
        figures: (config.question.figure_refs || []).map(toFigure),
        finalText: config.question.student_final_answer || "",
        final: symbolic(config.question.student_final_symbolic),
        dirty: false,
        saving: false,
        saved: false,
        error: "",

        init() {
          this.steps.forEach((step) => this.preview(step));
          this.figures.forEach((fig) => this.preview(fig));
          this.preview(this.final);
        },

        flagsFor(step) {
          return step.reviewFlags || [];
        },

        touch() {
          this.dirty = true;
          this.saved = false;
        },

        async preview(target) {
          const text = target.repr.trim();
          if (!text) {
            target.previewTex = null;
            return;
          }
          if (isFigureToken(target)) {
            target.previewTex = text;
            return;
          }
          try {
            const data = await window.mathGrader.requestJson("/api/preview", {
              method: "POST",
              body: JSON.stringify({ text }),
            });
            if (target.repr.trim() === text) target.previewTex = data.latex;
          } catch (exc) {
            target.previewTex = null;
          }
        },

        tex(el, latex, repr, kind) {
          const hasText = Boolean(repr && repr.trim());
          const figureOk =
            (kind || "") === "figure" || FIGURE_TOKEN.test((repr || "").trim());
          el.classList.toggle("preview-bad", hasText && latex === null && !figureOk);
          if (figureOk && hasText) {
            el.textContent = repr.trim();
            return;
          }
          if (latex && window.katex && latex !== PENDING && !figureOk) {
            window.katex.render(latex, el, { throwOnError: false });
          } else if (!hasText) {
            el.textContent = "—";
          } else {
            el.textContent = latex === PENDING ? "…" : "tidak terbaca SymPy";
          }
        },

        renumber() {
          this.steps.forEach((step, index) => {
            step.step_number = index + 1;
          });
        },

        addStep() {
          const last = this.steps[this.steps.length - 1];
          this.steps.push(
            toStep({
              step_number: this.steps.length + 1,
              raw_text: "",
              symbolic: null,
              role: null,
              confidence: null,
              page_number: last ? last.page_number : null,
            }),
          );
          this.renumber();
          this.touch();
        },

        removeStep(index) {
          this.steps.splice(index, 1);
          this.renumber();
          this.touch();
        },

        moveStep(index, delta) {
          const next = index + delta;
          if (next < 0 || next >= this.steps.length) return;
          const [row] = this.steps.splice(index, 1);
          this.steps.splice(next, 0, row);
          this.renumber();
          this.touch();
        },

        addFigure() {
          this.figures.push(
            toFigure({
              path: "",
              caption: "",
              page_number: null,
              symbolic: { kind: "figure", repr: "" },
            }),
          );
          this.touch();
        },

        removeFigure(index) {
          this.figures.splice(index, 1);
          this.touch();
        },

        payload() {
          const steps = this.steps.map(
            ({ key, kind, repr, previewTex, reviewFlags, ...rest }) => ({
              ...rest,
              role: rest.role || null,
              symbolic: toPayload(kind, repr),
            }),
          );
          const figure_refs = this.figures.map(
            ({ key, kind, repr, previewTex, path, caption, page_number }) => ({
              path: path || "",
              caption: caption || "",
              page_number,
              symbolic: toPayload(kind || "figure", repr),
            }),
          );
          return {
            ...this.original,
            student_steps: steps,
            student_final_answer: this.finalText,
            student_final_symbolic: toPayload(this.final.kind, this.final.repr),
            figure_refs,
          };
        },

        async save() {
          this.saving = true;
          this.error = "";
          try {
            const body = this.payload();
            const result = await window.mathGrader.requestJson(config.saveUrl, {
              method: "PUT",
              body: JSON.stringify(body),
            });
            if (result.errors && result.errors.length) {
              this.error = result.errors.join("; ");
              return;
            }
            this.original = body;
            this.dirty = false;
            this.saved = true;
          } catch (exc) {
            this.error = exc.message;
          } finally {
            this.saving = false;
          }
        },
      };
    });
  });
})();
