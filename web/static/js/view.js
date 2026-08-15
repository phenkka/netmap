// расставленную схему делают один раз, она переживает перезагрузку.
// отменяются перетаскивание и перестройка схемы

import { cy } from "./cy.js";
import { layoutLabels } from "./labels.js";
import { EASING, MOTION, PLACES_KEY, VIEW_KEY } from "./const.js";

const HISTORY_DEPTH = 50;
const history = [];
const future = [];
let beforeDrag = null;

export function snapshot() {
  const places = {};
  cy.nodes().forEach((node) => {
    places[node.id()] = { ...node.position() };
  });
  return places;
}

export function remember(before) {
  history.push(before);
  if (history.length > HISTORY_DEPTH) history.shift();
  future.length = 0;
}

function restore(places) {
  cy.nodes().forEach((node) => {
    const place = places[node.id()];
    if (place) {
      node.animate({ position: place }, { duration: MOTION, easing: EASING });
    }
  });
  setTimeout(() => {
    layoutLabels();
    // без этого отменённая расстановка вернётся после перезагрузки страницы
    savePlaces();
  }, MOTION + 20);
}

function undo() {
  if (history.length === 0) return;
  future.push(snapshot());
  restore(history.pop());
}

function redo() {
  if (future.length === 0) return;
  history.push(snapshot());
  restore(future.pop());
}

export function savePlaces() {
  try {
    localStorage.setItem(PLACES_KEY, JSON.stringify(snapshot()));
  } catch (error) {
    /* инкогнито, схема просто не запомнится */
  }
}

export function savedPlaces() {
  try {
    return JSON.parse(localStorage.getItem(PLACES_KEY) || "{}");
  } catch (error) {
    return {};
  }
}

let viewTimer = null;

function saveView() {
  clearTimeout(viewTimer);
  viewTimer = setTimeout(() => {
    try {
      localStorage.setItem(
        VIEW_KEY,
        JSON.stringify({ zoom: cy.zoom(), pan: cy.pan() })
      );
    } catch (error) {
      /* инкогнито */
    }
  }, 300);
}

export function restoreView() {
  try {
    const view = JSON.parse(localStorage.getItem(VIEW_KEY) || "null");
    if (!view || !view.zoom) return false;
    cy.viewport({ zoom: view.zoom, pan: view.pan });
    return true;
  } catch (error) {
    return false;
  }
}

cy.on("grab", "node", () => {
  beforeDrag = snapshot();
});

cy.on("dragfree", "node", () => {
  if (beforeDrag) remember(beforeDrag);
  beforeDrag = null;
});

cy.on("zoom pan", saveView);
cy.on("dragfree", "node", savePlaces);

document.addEventListener("keydown", (event) => {
  const typing = ["INPUT", "TEXTAREA"].includes(event.target.tagName);
  if (typing || !(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "z") {
    return;
  }
  event.preventDefault();
  if (event.shiftKey) redo();
  else undo();
});
