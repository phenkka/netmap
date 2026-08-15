import { api } from "./api.js";
import { state } from "./state.js";
import { loadGraph } from "./map.js";
import { applyOpenState, renderList } from "./tree.js";

let lastDevices = "";

async function loadDevices() {
  state.devices = (await api("/api/devices")).devices;

  // перерисовка списка сбрасывает наведение и выделение, поэтому делаем её
  // только когда данные действительно поменялись
  const signature = JSON.stringify(state.devices);
  if (signature === lastDevices) return;
  lastDevices = signature;
  renderList();
  applyOpenState();
}

export async function refreshAll() {
  await loadDevices();
  await loadGraph();
}
