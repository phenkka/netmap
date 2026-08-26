import { api } from "./api.js";
import { state } from "./state.js";
import { loadGraph } from "./map.js";
import { updateList } from "./tree.js";

let lastDevices = "";

async function loadDevices() {
  state.devices = (await api("/api/devices")).devices;

  const signature = JSON.stringify(state.devices);
  if (signature === lastDevices) return;
  lastDevices = signature;
  updateList();
}

export async function refreshAll() {
  await loadDevices();
  await loadGraph();
}
