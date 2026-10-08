// Transcription review: one Alpine editor per question.json, KaTeX preview of the SymPy form.
(function () {
  "use strict";

  const PENDING = undefined; // previewTex: undefined = waiting, null = unparseable

  window.addEventListener("beforeunload", (event) => {
    if (document.querySelector('.review-item[data-dirty="true"]')) {
      event.preventDefault();
      event.returnValue = "";
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
        key: ++keySeq,
      });
      const toPayload = (kind, repr) => (kind ? { kind, repr: repr.trim() } : null);

      return {
        original: config.question,
        steps: config.question.student_steps.map(toStep),
        finalText: config.question.student_final_answer || "",
        final: symbolic(config.question.student_final_symbolic),
        dirty: false,
        saving: false,
        saved: false,
        error: "",

        init() {
          this.steps.forEach((step) => this.preview(step));
          this.preview(this.final);
        },

        flagsFor(step) {
          return config.flags[String(step.step_number)] || [];
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

        tex(el, latex, repr) {
          const hasText = Boolean(repr && repr.trim());
          el.classList.toggle("preview-bad", hasText && latex === null);
          if (latex && window.katex) {
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

        payload() {
          const steps = this.steps.map(({ key, kind, repr, previewTex, ...rest }) => ({
            ...rest,
            role: rest.role || null,
            symbolic: toPayload(kind, repr),
          }));
          return {
            ...this.original,
            student_steps: steps,
            student_final_answer: this.finalText,
            student_final_symbolic: toPayload(this.final.kind, this.final.repr),
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
