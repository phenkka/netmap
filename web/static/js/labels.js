// каждая подпись считается прямоугольником на экране. имя устройства
// переезжает на свободную сторону, подпись порта без места не рисуется

import { cy } from "./cy.js";
import { GAP, ICON_BODY, NODE_FONT, PORT_FONT, PORT_OFFSET } from "./const.js";

function textBox(text, cx, cy_, fontSize) {
  const lines = String(text || "").split("\n");
  const width = Math.max(...lines.map((line) => line.length)) * fontSize * 0.6 + 6;
  const height = lines.length * fontSize * 1.25 + 6;
  return {
    x1: cx - width / 2,
    y1: cy_ - height / 2,
    x2: cx + width / 2,
    y2: cy_ + height / 2,
  };
}

function busyness(dir, leaving) {
  return leaving.reduce(
    (sum, way) => sum + Math.max(0, way[0] * dir[0] + way[1] * dir[1]),
    0
  );
}

function crosses(a, b) {
  return !(a.x2 < b.x1 || b.x2 < a.x1 || a.y2 < b.y1 || b.y2 < a.y1);
}

function onScreen(point) {
  const zoom = cy.zoom();
  const pan = cy.pan();
  return { x: point.x * zoom + pan.x, y: point.y * zoom + pan.y };
}

export function layoutLabels() {
  const zoom = cy.zoom();
  const taken = [];

  // размер берём фактический, под курсором значок крупнее
  const halfOf = (node) => ((node.width() * ICON_BODY) / 2) * zoom;

  cy.nodes().forEach((node) => {
    const p = node.renderedPosition();
    const half = halfOf(node);
    taken.push({ x1: p.x - half, y1: p.y - half, x2: p.x + half, y2: p.y + half });
  });

  cy.nodes().forEach((node) => {
    const p = node.renderedPosition();
    const size = textBox(node.data("label"), 0, 0, NODE_FONT * zoom);
    const w = (size.x2 - size.x1) / 2;
    const h = (size.y2 - size.y1) / 2;
    const away = halfOf(node) + GAP * zoom;

    const options = [
      { valign: "bottom", halign: "center", x: p.x, y: p.y + away + h, mx: 0, my: GAP, dir: [0, 1] },
      { valign: "top", halign: "center", x: p.x, y: p.y - away - h, mx: 0, my: -GAP, dir: [0, -1] },
      { valign: "center", halign: "right", x: p.x + away + w, y: p.y, mx: GAP, my: 0, dir: [1, 0] },
      { valign: "center", halign: "left", x: p.x - away - w, y: p.y, mx: -GAP, my: 0, dir: [-1, 0] },
    ];

    // сторону выбираем ту, куда уходит меньше связей
    const leaving = [];
    node.connectedEdges().forEach((link) => {
      const other = link.source().same(node) ? link.target() : link.source();
      const q = other.renderedPosition();
      const len = Math.hypot(q.x - p.x, q.y - p.y) || 1;
      leaving.push([(q.x - p.x) / len, (q.y - p.y) / len]);
    });
    options.sort((a, b) => busyness(a.dir, leaving) - busyness(b.dir, leaving));

    let best = null;
    let fewest = Infinity;
    for (const option of options) {
      const area = {
        x1: option.x - w,
        y1: option.y - h,
        x2: option.x + w,
        y2: option.y + h,
      };
      const clashes = taken.filter((busy) => crosses(busy, area)).length;
      if (clashes < fewest) {
        fewest = clashes;
        best = { ...option, area };
        if (clashes === 0) break;
      }
    }

    node.style({
      "text-valign": best.valign,
      "text-halign": best.halign,
      "text-margin-x": best.mx,
      "text-margin-y": best.my,
    });
    taken.push(best.area);
  });

  // связи выбранного идут первыми, чтобы при нехватке места пропадали чужие
  const ordered = cy
    .edges(".ports")
    .toArray()
    .concat(cy.edges().not(".ports").toArray());

  ordered.forEach((link) => {
    // концы линии лежат на краю значка, от них и считается отступ
    const start = onScreen(link.sourceEndpoint());
    const finish = onScreen(link.targetEndpoint());

    for (const end of ["source", "target"]) {
      const near = end === "source" ? start : finish;
      const far = end === "source" ? finish : start;
      const dx = far.x - near.x;
      const dy = far.y - near.y;
      const length = Math.hypot(dx, dy) || 1;
      const shift = PORT_OFFSET * zoom;
      const text = link.data(end === "source" ? "source_short" : "target_short");
      const area = textBox(
        text,
        near.x + (dx / length) * shift,
        near.y + (dy / length) * shift,
        PORT_FONT * zoom
      );

      const clash = taken.some((busy) => crosses(busy, area));
      link.style(end === "source" ? "source-label" : "target-label", clash ? "" : text);
      if (!clash) taken.push(area);
    }
  });
}

let pending = null;

export function scheduleLabels() {
  if (pending) return;
  pending = requestAnimationFrame(() => {
    pending = null;
    layoutLabels();
  });
}

cy.on("position", "node", scheduleLabels);
cy.on("zoom pan", scheduleLabels);
