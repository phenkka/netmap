import { api, setStatus } from "./js/api.js";
import { cy } from "./js/cy.js";
import { state } from "./js/state.js";
import { layoutLabels } from "./js/labels.js";
import {
  focusNode,
  pulseNode,
  restoreSize,
  showPorts,
  sizeNode,
  syncGrid,
} from "./js/map.js";
import { clearPanel, renderList, showDevice } from "./js/tree.js";
import { fitActive, openTerminal } from "./js/terminal.js";
import { refreshAll } from "./js/load.js";
import { DOUBLE_TAP, FOCUS_WAIT, HOVER_SCALE, REFRESH_EVERY } from "./js/const.js";
import { showAccount } from "./js/settings.js";
import "./js/theme.js";
import "./js/view.js";
// журнал заводит свою вкладку первым, поэтому и импортируется раньше терминала
import "./js/journal.js";
import "./js/bulk.js";

let lastTap = { id: null, at: 0 };
let focusTimer = null;

cy.on("tap", "node", (event) => {
  const node = event.target;
  const id = node.id();
  const now = Date.now();

  clearTimeout(focusTimer);

  if (lastTap.id === id && now - lastTap.at < DOUBLE_TAP) {
    lastTap = { id: null, at: 0 };
    pulseNode(node);
    const device = state.devices.find((d) => d.ip === id);
    if (device && device.authorized) {
      // центрирование внутри openTerminal, там карта уже пересчитана
      openTerminal(device.ip, device.hostname || device.ip);
    } else {
      setStatus("терминал открывается только у авторизованного устройства");
      focusNode(node);
    }
    return;
  }

  lastTap = { id, at: now };
  showDevice(id);
  // после showDevice, иначе выбор перебьёт толчок своим размером
  pulseNode(node);
  // ждём, не окажется ли нажатие первым из двойного, иначе камера дёрнется дважды
  focusTimer = setTimeout(() => focusNode(node), FOCUS_WAIT);
});

cy.on("mouseover", "node", (event) => {
  cy.container().style.cursor = "pointer";
  sizeNode(event.target, HOVER_SCALE);
  showPorts(event.target);
});

cy.on("mouseout", "node", (event) => {
  cy.container().style.cursor = "";
  restoreSize(event.target);
  const chosen = state.selected ? cy.getElementById(state.selected) : null;
  showPorts(chosen && chosen.length ? chosen : null);
});

cy.on("tap", (event) => {
  if (event.target === cy) clearPanel();
});

window.addEventListener("resize", () => {
  cy.resize();
  fitActive();
  layoutLabels();
});

// обход сети ведёт сервер в фоне, страница только читает найденное
async function firstScan() {
  try {
    const settings = await api("/api/settings");
    state.subnet = settings.subnet;
    showAccount(settings);
    // список рисуется раньше, чем приходят настройки, и остаётся без имени сети
    renderList();
    if (settings.subnet) {
      await api("/api/scan", {
        method: "POST",
        body: JSON.stringify({ subnet: settings.subnet }),
      });
    }
  } catch (error) {
    setStatus(error.message);
  }
  await refreshAll();
}

document.addEventListener("netmap:refresh", () => {
  refreshAll().catch(() => {});
});

syncGrid();
setInterval(refreshAll, REFRESH_EVERY);
refreshAll();
firstScan();
