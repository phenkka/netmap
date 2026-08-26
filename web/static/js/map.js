import { cy } from "./cy.js";
import { api } from "./api.js";
import { state } from "./state.js";
import { layoutLabels, scheduleLabels } from "./labels.js";
import { remember, restoreView, savePlaces, savedPlaces, snapshot } from "./view.js";
import {
  EASING,
  FOCUS_MOTION,
  FOCUS_ZOOM,
  HOVER_SCALE,
  ICON_SIZE,
  MOTION,
  PICKED_SCALE,
  TAP_SCALE,
} from "./const.js";

const mapBox = document.getElementById("map");

// клетка двигается и масштабируется вместе со схемой
export function syncGrid() {
  const zoom = cy.zoom();
  const pan = cy.pan();
  const small = 32 * zoom;
  const big = 160 * zoom;
  mapBox.style.backgroundSize =
    `${big}px ${big}px, ${big}px ${big}px, ${small}px ${small}px, ${small}px ${small}px`;
  mapBox.style.backgroundPosition = `${pan.x}px ${pan.y}px`;
}

cy.on("zoom pan", syncGrid);

// в одном кадре поставленный и снятый класс перехода не даёт
function arrive(added) {
  added.addClass("arriving");
  requestAnimationFrame(() => added.removeClass("arriving"));
}

// ethernet-1/1 → eth1/1, полное имя остаётся в карточке
function shortPort(name) {
  const match = String(name).match(/^([A-Za-z]*)[_-]*(.*)$/);
  if (!match || !match[2]) return String(name);
  return match[1].slice(0, 3) + match[2];
}

function nodeLabel(node) {
  if (node.id.startsWith("lldp:")) return node.label;
  return node.label === node.id ? node.id : `${node.label}\n${node.id}`;
}

// корень это устройство с наибольшим числом связей, обычно ядро
function pickRoot() {
  if (state.rootId && cy.getElementById(state.rootId).length) return state.rootId;
  let best = null;
  cy.nodes().forEach((node) => {
    if (!best || node.degree() > best.degree()) best = node;
  });
  return best ? best.id() : null;
}

export function fitView(smooth = false) {
  if (cy.nodes().length === 0) return;

  // помещается — показываем в натуральную величину, иначе ужимаем
  const settle = () => {
    if (cy.zoom() > 1) {
      cy.zoom(1);
      cy.center();
    }
    layoutLabels();
  };

  if (smooth) {
    cy.animate(
      { fit: { eles: cy.elements(), padding: 120 } },
      { duration: MOTION, easing: EASING, complete: settle }
    );
  } else {
    cy.fit(undefined, 120);
    settle();
  }
}

export function relayout({ track = true, smooth = true, fit = true } = {}) {
  const before = track && cy.nodes().length ? snapshot() : null;

  // без связей дерево строить не из чего
  const plan =
    cy.edges().length === 0
      ? { name: "grid", rows: 1, padding: 60 }
      : {
          name: "breadthfirst",
          directed: false,
          roots: pickRoot() ? [pickRoot()] : undefined,
          spacingFactor: 1.8,
          padding: 70,
        };

  // без границ раскладка уложит схему в видимое окно и она уедет
  const area = cy.elements().length ? cy.elements().boundingBox() : undefined;

  const layout = cy.layout({
    ...plan,
    boundingBox: fit ? undefined : area,
    // подгонку масштаба раскладка делает сама, нам это не нужно
    fit: false,
    animate: smooth,
    animationDuration: MOTION,
    animationEasing: EASING,
  });

  layout.promiseOn("layoutstop").then(() => {
    if (fit) fitView(smooth);
    else layoutLabels();
    savePlaces();
  });
  layout.run();

  if (before) remember(before);
}

// обновляем по разнице: при пересоздании новые узлы падают в ноль
// и схема схлопывается
export async function loadGraph() {
  const graph = await api("/api/graph");
  const had = cy.nodes().length > 0;
  const places = savedPlaces();
  let appeared = 0;

  const liveNodes = new Set();
  for (const node of graph.nodes) {
    liveNodes.add(node.id);
    const data = { ...node, label: nodeLabel(node) };
    const known = cy.getElementById(node.id);
    if (known.length) {
      known.data(data);
      continue;
    }
    // устройство с прошлого раза возвращается на своё место
    const place = places[node.id];
    cy.add(place ? { group: "nodes", data, position: place } : { group: "nodes", data });
    if (!place) appeared += 1;
  }

  const liveEdges = new Set();
  let linked = 0;
  for (const link of graph.edges) {
    liveEdges.add(link.id);
    const data = {
      ...link,
      source_short: shortPort(link.source_port),
      target_short: shortPort(link.target_port),
    };
    const known = cy.getElementById(link.id);
    if (known.length) known.data(data);
    else {
      arrive(cy.add({ group: "edges", data }));
      linked += 1;
    }
  }

  cy.nodes().forEach((node) => {
    if (!liveNodes.has(node.id())) node.remove();
  });
  cy.edges().forEach((link) => {
    if (!liveEdges.has(link.id())) link.remove();
  });

  // до первой связи схема лежит решёткой в один ряд, дерево строить не из чего.
  // связи приходят позже узлов, по мере входа на устройства, и без пересчёта
  // схема так и остаётся шеренгой
  if (appeared > 0 || linked > 0) {
    relayout({ track: false, smooth: had });
  } else {
    if (!had) restoreView();
    layoutLabels();
  }
}

export function showPorts(node) {
  cy.edges().removeClass("ports");
  if (node) node.connectedEdges().addClass("ports");
  layoutLabels();
}

export function sizeNode(node, scale) {
  if (!node || !node.length) return;
  node.stop();
  node.animate(
    { style: { width: ICON_SIZE * scale, height: ICON_SIZE * scale } },
    { duration: 150, easing: "ease-out", step: scheduleLabels }
  );
}

export function restoreSize(node) {
  sizeNode(node, node.id() === state.selected ? PICKED_SCALE : 1);
}

// нажатие само по себе незаметно: курсор уже над узлом и тот увеличен
// наведением, поэтому даём короткий толчок и возвращаем к размеру наведения
export function pulseNode(node) {
  sizeNode(node, TAP_SCALE);
  setTimeout(() => sizeNode(node, HOVER_SCALE), 160);
}

export function focusNode(node) {
  cy.stop();
  cy.animate(
    // сильно отдалённую схему подтягиваем, приближённую не трогаем
    { center: { eles: node }, zoom: Math.max(cy.zoom(), FOCUS_ZOOM) },
    { duration: FOCUS_MOTION, easing: EASING, step: scheduleLabels, complete: layoutLabels }
  );
}
