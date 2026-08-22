// нижняя панель на манер вскода: вкладки слева, журнал всегда первый и
// закрыть его нельзя, остальные вкладки заводит терминал

import { cy } from "./cy.js";
import { layoutLabels } from "./labels.js";

const dock = document.getElementById("dock");
const list = document.getElementById("dock-list");
const body = document.getElementById("dock-body");

const tabs = new Map();
let active = null;

export function addTab(tab) {
  tabs.set(tab.id, { closable: true, ...tab });
  render();
}

export function removeTab(id) {
  const tab = tabs.get(id);
  if (!tab || !tab.closable) return;

  tab.onClose?.();
  tab.pane.remove();
  tabs.delete(id);

  if (active === id) {
    const next = tabs.keys().next();
    active = next.done ? null : next.value;
  }
  showTab(active);
}

export function showTab(id) {
  if (!tabs.has(id)) return;
  active = id;
  for (const tab of tabs.values()) {
    tab.pane.hidden = tab.id !== id;
  }
  render();
  tabs.get(id).onShow?.();
}

export function markTab(id, state) {
  const tab = tabs.get(id);
  if (!tab) return;
  tab.state = state;
  render();
}

export function openDock(id) {
  const wasHidden = dock.hidden;
  dock.hidden = false;
  if (id) showTab(id);
  else if (active) showTab(active);
  if (wasHidden) resized();
}

export function hideDock() {
  dock.hidden = true;
  resized();
}

export function toggleDock() {
  if (dock.hidden) openDock();
  else hideDock();
}

export function dockHidden() {
  return dock.hidden;
}

export function activeTab() {
  return active;
}

export function paneFor(id) {
  const pane = document.createElement("div");
  pane.className = "dock-pane";
  pane.dataset.pane = id;
  pane.hidden = true;
  body.append(pane);
  return pane;
}

function resized() {
  cy.resize();
  layoutLabels();
}

function render() {
  list.textContent = "";
  for (const tab of tabs.values()) {
    const button = document.createElement("button");
    button.className = "dock-tab" + (tab.state ? ` ${tab.state}` : "");
    if (tab.id === active) button.classList.add("active");

    if (tab.state) {
      const live = document.createElement("i");
      live.className = "live";
      button.append(live);
    }

    const name = document.createElement("span");
    name.textContent = tab.label;
    button.append(name);

    if (tab.closable) {
      const shut = document.createElement("span");
      shut.className = "shut";
      shut.textContent = "✕";
      shut.title = "Закрыть вкладку";
      shut.addEventListener("click", (event) => {
        event.stopPropagation();
        removeTab(tab.id);
      });
      button.append(shut);
    }

    button.addEventListener("click", () => showTab(tab.id));
    list.append(button);
  }
}

document.getElementById("dock-hide").addEventListener("click", hideDock);
document.getElementById("dock-toggle").addEventListener("click", toggleDock);

document.getElementById("dock-grip").addEventListener("mousedown", (event) => {
  event.preventDefault();
  const startY = event.clientY;
  const startHeight = dock.offsetHeight;

  const move = (moveEvent) => {
    const height = Math.min(
      Math.max(startHeight + startY - moveEvent.clientY, 120),
      window.innerHeight - 220
    );
    dock.style.height = `${height}px`;
    cy.resize();
    for (const tab of tabs.values()) tab.onResize?.();
  };
  const stop = () => {
    document.removeEventListener("mousemove", move);
    document.removeEventListener("mouseup", stop);
    layoutLabels();
  };

  document.addEventListener("mousemove", move);
  document.addEventListener("mouseup", stop);
});
