// Manual crop editor: Konva stage over the rendered page, boxes kept in page pixels.
// The stage is scaled by `zoom`, so pointer positions read through
// getRelativePointerPosition() are already in natural-image pixels.
(function () {
  "use strict";

  const MIN_SIDE_PX = 4; // matches app.functions.regions_artifact.MIN_REGION_SIDE_PX
  const COLORS = { solution: "#2563eb", figure: "#16a34a", selected: "#f59e0b" };
  const MIN_ZOOM = 0.1;
  const MAX_ZOOM = 4;

  const clamp = (value, low, high) => Math.min(Math.max(value, low), high);

  document.addEventListener("alpine:init", () => {
    window.Alpine.data("cropEditor", (config) => {
      const W = config.page.width;
      const H = config.page.height;
      // Konva objects stay outside Alpine's reactive proxy.
      let stage = null;
      let boxLayer = null;
      let transformer = null;
      let seq = 0;

      const toBoxes = (regions) =>
        [...regions]
          .sort((a, b) => a.order - b.order)
          .map((r) => ({
            id: ++seq,
            x: r.region.x,
            y: r.region.y,
            width: r.region.width,
            height: r.region.height,
            type: r.type,
            question_number: r.question_number || 0,
          }));

      return {
        boxes: toBoxes(config.page.regions),
        savedCount: config.page.regions.length,
        savedSource: config.page.source,
        selectedId: null,
        zoom: 1,
        dirty: false,
        saving: false,
        error: "",

        init() {
          stage = new Konva.Stage({ container: this.$refs.stage, width: W, height: H });
          const imageLayer = new Konva.Layer();
          boxLayer = new Konva.Layer();
          stage.add(imageLayer, boxLayer);
          transformer = new Konva.Transformer({
            rotateEnabled: false,
            flipEnabled: false,
            keepRatio: false,
            ignoreStroke: true,
            borderStroke: COLORS.selected,
            anchorStroke: COLORS.selected,
            anchorSize: 9,
            boundBoxFunc: (oldBox, newBox) => {
              const min = MIN_SIDE_PX * stage.scaleX();
              return Math.abs(newBox.width) < min || Math.abs(newBox.height) < min ? oldBox : newBox;
            },
          });
          boxLayer.add(transformer);

          const image = new Image();
          image.onload = () => {
            imageLayer.add(new Konva.Image({ image, x: 0, y: 0, width: W, height: H }));
            this.fit();
          };
          image.src = config.imageUrl;

          this.bindDrawing(imageLayer);
          window.addEventListener("beforeunload", (event) => {
            if (this.dirty) {
              event.preventDefault();
              event.returnValue = "";
            }
          });
          this.draw();
        },

        pointer() {
          const p = stage.getRelativePointerPosition();
          return { x: clamp(p.x, 0, W), y: clamp(p.y, 0, H) };
        },

        bindDrawing(imageLayer) {
          let start = null;
          let ghost = null;
          stage.on("mousedown touchstart", (event) => {
            if (event.target !== stage && event.target.getLayer() !== imageLayer) return;
            this.select(null);
            start = this.pointer();
            ghost = new Konva.Rect({
              ...start,
              width: 0,
              height: 0,
              stroke: COLORS.solution,
              strokeWidth: 2,
              dash: [6, 4],
              strokeScaleEnabled: false,
              listening: false,
            });
            boxLayer.add(ghost);
          });
          stage.on("mousemove touchmove", () => {
            if (!start) return;
            const p = this.pointer();
            ghost.setAttrs({
              x: Math.min(start.x, p.x),
              y: Math.min(start.y, p.y),
              width: Math.abs(p.x - start.x),
              height: Math.abs(p.y - start.y),
            });
            boxLayer.batchDraw();
          });
          const finish = () => {
            if (!start) return;
            const rect = { x: ghost.x(), y: ghost.y(), width: ghost.width(), height: ghost.height() };
            ghost.destroy();
            start = null;
            ghost = null;
            if (rect.width >= MIN_SIDE_PX && rect.height >= MIN_SIDE_PX) {
              const box = { id: ++seq, ...rect, type: "solution", question_number: 0 };
              this.boxes.push(box);
              this.selectedId = box.id;
              this.markDirty();
            } else {
              boxLayer.batchDraw();
            }
          };
          stage.on("mouseup touchend mouseleave", finish);
        },

        draw() {
          if (!stage) return;
          transformer.nodes([]);
          boxLayer.find(".box").forEach((node) => node.destroy());
          const fontSize = 14 / stage.scaleX();
          this.boxes.forEach((box, index) => {
            const selected = box.id === this.selectedId;
            const color = selected ? COLORS.selected : COLORS[box.type] || COLORS.solution;
            const group = new Konva.Group({ name: "box" });
            const rect = new Konva.Rect({
              id: "box-" + box.id,
              x: box.x,
              y: box.y,
              width: box.width,
              height: box.height,
              stroke: color,
              strokeWidth: 2,
              strokeScaleEnabled: false,
              fill: color + "1a",
              draggable: true,
            });
            const label = new Konva.Label({ x: box.x, y: box.y, listening: false });
            label.add(new Konva.Tag({ id: "tag-" + box.id, fill: color }));
            label.add(
              new Konva.Text({
                text: "#" + (index + 1) + (box.question_number ? " · soal " + box.question_number : ""),
                fill: "#fff",
                fontSize,
                padding: fontSize / 4,
              }),
            );
            rect.on("mousedown touchstart", () => this.select(box.id));
            rect.on("dragmove", () => {
              rect.position({
                x: clamp(rect.x(), 0, W - rect.width() * rect.scaleX()),
                y: clamp(rect.y(), 0, H - rect.height() * rect.scaleY()),
              });
              label.position(rect.position());
            });
            rect.on("transform", () => label.position(rect.position()));
            rect.on("dragend transformend", () => this.commitShape(box.id, rect));
            group.add(rect, label);
            boxLayer.add(group);
          });
          this.attachTransformer();
        },

        commitShape(id, rect) {
          const box = this.boxes.find((b) => b.id === id);
          if (!box) return;
          const x = clamp(rect.x(), 0, W);
          const y = clamp(rect.y(), 0, H);
          box.x = x;
          box.y = y;
          box.width = Math.min(rect.width() * rect.scaleX(), W - x);
          box.height = Math.min(rect.height() * rect.scaleY(), H - y);
          this.markDirty();
        },

        attachTransformer() {
          const rect = this.selectedId ? stage.findOne("#box-" + this.selectedId) : null;
          transformer.nodes(rect ? [rect] : []);
          transformer.moveToTop();
          boxLayer.batchDraw();
        },

        // Restyle in place: rebuilding shapes on mousedown would cancel the drag.
        select(id) {
          if (this.selectedId === id || !stage) return;
          this.selectedId = id;
          this.boxes.forEach((box) => {
            const color = box.id === id ? COLORS.selected : COLORS[box.type] || COLORS.solution;
            const rect = stage.findOne("#box-" + box.id);
            const tag = stage.findOne("#tag-" + box.id);
            if (rect) rect.setAttrs({ stroke: color, fill: color + "1a" });
            if (tag) tag.fill(color);
          });
          this.attachTransformer();
        },

        markDirty() {
          this.dirty = true;
          this.draw();
        },

        move(index, delta) {
          const target = index + delta;
          if (target < 0 || target >= this.boxes.length) return;
          const [box] = this.boxes.splice(index, 1);
          this.boxes.splice(target, 0, box);
          this.markDirty();
        },

        remove(id) {
          this.boxes = this.boxes.filter((b) => b.id !== id);
          if (this.selectedId === id) this.selectedId = null;
          this.markDirty();
        },

        sortReading() {
          this.boxes = [...this.boxes].sort((a, b) => a.y - b.y || a.x - b.x);
          this.markDirty();
        },

        onKey(event) {
          if (event.target.closest("input, select, textarea")) return;
          if ((event.key === "Delete" || event.key === "Backspace") && this.selectedId) {
            event.preventDefault();
            this.remove(this.selectedId);
          } else if (event.key === "Escape") {
            this.select(null);
          }
        },

        setZoom(value) {
          this.zoom = clamp(value, MIN_ZOOM, MAX_ZOOM);
          stage.scale({ x: this.zoom, y: this.zoom });
          stage.size({ width: W * this.zoom, height: H * this.zoom });
          this.draw();
        },

        zoomBy(factor) {
          this.setZoom(this.zoom * factor);
        },

        fit() {
          const available = this.$refs.wrap.clientWidth - 4;
          this.setZoom(available > 0 ? available / W : 1);
        },

        payload() {
          return {
            regions: this.boxes.map((b) => ({
              x: Math.round(b.x),
              y: Math.round(b.y),
              width: Math.round(b.width),
              height: Math.round(b.height),
              type: b.type,
              question_number: Number(b.question_number) || 0,
            })),
          };
        },

        applyServer(data) {
          this.boxes = toBoxes(data.page.regions);
          this.savedCount = data.page.regions.length;
          this.savedSource = data.page.source;
          this.selectedId = null;
          this.dirty = false;
          this.draw();
        },

        async save() {
          this.saving = true;
          this.error = "";
          try {
            const data = await window.mathGrader.requestJson(config.regionsUrl, {
              method: "PUT",
              body: JSON.stringify(this.payload()),
            });
            this.applyServer(data);
            window.htmx.ajax("GET", config.thumbsUrl, { target: "#thumbs", swap: "innerHTML" });
            window.mathGrader.flash(
              "ok",
              "Halaman " + config.page.page_number + ": " + data.crop_names.length + " crop disimpan",
            );
          } catch (exc) {
            this.error = exc.message;
          } finally {
            this.saving = false;
          }
        },

        async reload() {
          this.error = "";
          try {
            this.applyServer(await window.mathGrader.requestJson(config.regionsUrl, { method: "GET" }));
          } catch (exc) {
            this.error = exc.message;
          }
        },

        guardLeave(event) {
          if (!this.dirty) return;
          if (window.confirm("Perubahan kotak belum disimpan. Tinggalkan halaman?")) {
            this.dirty = false;
          } else {
            event.preventDefault();
          }
        },
      };
    });
  });
})();
