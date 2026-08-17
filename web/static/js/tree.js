// корень это сеть, внутри устройства со значком своего типа. раскрытое
// устройство выделяется на карте, и наоборот

import { ICONS } from "./icons.js";
import { api } from "./api.js";
import { cy } from "./cy.js";
import { state } from "./state.js";
import { themeColor } from "./colors.js";
import { relayout, showPorts, sizeNode } from "./map.js";
import { openTerminal } from "./terminal.js";
import { refreshAll } from "./load.js";
import { PICKED_SCALE } from "./const.js";

const KIND = {
  switch: "коммутатор",
  router: "маршрутизатор",
  multilayer: "коммутатор с маршрутизацией",
  firewall: "межсетевой экран",
  wifi: "точка доступа",
};

const LLDP = {
  enabled: "LLDP был выключен, продукт включил его при входе. Без него соседи не видны.",
  busy: "LLDP выключен, но включать не стали: на устройстве есть незакоммиченная правка, и наш commit применил бы её. Повторите вход, когда правку сохранят или отменят.",
  failed: "LLDP выключен, включить не удалось. Пока он выключен, соседи этого устройства не видны.",
};

const tree = document.getElementById("tree");
let netOpen = localStorage.getItem("net-open") !== "no";

const CARET =
  '<svg class="caret" viewBox="0 0 12 12" fill="none" stroke="currentColor" ' +
  'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' +
  '<path d="M4.5 2.5 8 6l-3.5 3.5"/></svg>';

export function renderList() {
  tree.textContent = "";

  const net = document.createElement("li");
  net.className = "net" + (netOpen ? " open" : "");

  const head = document.createElement("button");
  head.className = "row";
  head.innerHTML = CARET;

  const title = document.createElement("span");
  title.className = "name";
  title.textContent = document.getElementById("subnet").value.trim();

  const count = document.createElement("span");
  count.className = "count";
  count.textContent = state.devices.length || "";

  head.append(title, count);
  head.addEventListener("click", () => {
    netOpen = !netOpen;
    localStorage.setItem("net-open", netOpen ? "yes" : "no");
    net.classList.toggle("open", netOpen);
  });

  const fold = document.createElement("div");
  fold.className = "fold";
  const inner = document.createElement("div");
  inner.className = "inner";
  const items = document.createElement("ul");

  for (const device of state.devices) {
    items.append(deviceRow(device));
  }

  inner.append(items);
  fold.append(inner);
  net.append(head, fold);
  tree.append(net);
}

function deviceRow(device) {
  const item = document.createElement("li");
  item.className = "device" + (device.ip === state.selected ? " open" : "");
  item.dataset.ip = device.ip;

  const row = document.createElement("button");
  row.className = "row" + (device.ip === state.selected ? " picked" : "");

  const icon = document.createElement("img");
  icon.src = (ICONS[device.type] || ICONS.unknown)(
    device.authorized ? themeColor("--pos") : themeColor("--neg")
  );

  const name = document.createElement("span");
  name.className = "name";
  name.textContent = device.hostname || device.ip;

  row.append(icon, name);
  row.addEventListener("click", () => toggleDevice(device.ip));

  const fold = document.createElement("div");
  fold.className = "fold";
  const inner = document.createElement("div");
  inner.className = "inner";
  const card = document.createElement("div");
  card.className = "card";
  card.append(deviceDetails(device));
  inner.append(card);
  fold.append(inner);

  item.append(row, fold);
  return item;
}

function field(label, value) {
  const dt = document.createElement("dt");
  dt.textContent = label;
  const dd = document.createElement("dd");
  dd.textContent = value;
  return [dt, dd];
}

function deviceDetails(device) {
  const box = document.createElement("div");

  const kind = KIND[device.type];

  const list = document.createElement("dl");
  list.append(
    ...field("Адрес", device.ip),
    ...field("MAC", device.mac || "нет данных"),
    ...field("Производитель", device.vendor || device.vendor_guess || "не определён"),
    ...field("Тип", kind || "уточнится после входа")
  );
  if (device.model) list.append(...field("Модель", device.model));
  if (device.version) list.append(...field("Версия", device.version));
  box.append(list);

  if (LLDP[device.lldp]) {
    const note = document.createElement("p");
    note.className = "hint";
    note.textContent = LLDP[device.lldp];
    box.append(note);
  }

  if (!kind) {
    const hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent =
      "MAC-адрес выдаёт производителя, но не тип: у Nokia и Cisco есть и коммутаторы, " +
      "и маршрутизаторы. Тип берётся из модели устройства, а её видно только после входа.";
    box.append(hint);
  }

  box.append(
    button("Сделать корнем схемы", "secondary", () => {
      state.rootId = device.ip;
      localStorage.setItem("root", state.rootId);
      relayout({ fit: false });
    })
  );

  if (device.neighbors && device.neighbors.length) {
    const title = document.createElement("h3");
    title.textContent = "Соседи по LLDP";
    const table = document.createElement("table");
    table.className = "neighbors";
    for (const link of device.neighbors) {
      const row = table.insertRow();
      row.insertCell().textContent = link.local_port;
      row.insertCell().textContent = `${link.remote_name} ${link.remote_port}`;
    }
    box.append(title, table);
  }

  if (device.authorized) {
    box.append(
      button("Терминал", "", () =>
        openTerminal(device.ip, device.hostname || device.ip)
      ),
      button("Забыть учётные данные", "secondary", () => forgetDevice(device.ip))
    );
  } else {
    box.append(loginForm(device));
  }

  return box;
}

function button(text, extra, action) {
  const element = document.createElement("button");
  element.textContent = text;
  element.className = "wide " + extra;
  element.addEventListener("click", action);
  return element;
}

function loginForm(device) {
  const form = document.createElement("form");

  const title = document.createElement("h3");
  title.textContent = "Авторизация";

  const login = document.createElement("input");
  login.placeholder = "Логин";
  login.autocomplete = "off";

  const secret = document.createElement("input");
  secret.type = "password";
  secret.placeholder = "Пароль";
  secret.autocomplete = "off";

  const submit = document.createElement("button");
  submit.type = "submit";
  submit.className = "wide";
  submit.textContent = "Войти";

  const error = document.createElement("p");
  error.className = "error";
  error.textContent = device.error || "";

  form.append(title, login, secret, submit, error);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.textContent = "проверяю доступ";
    try {
      await api(`/api/devices/${device.ip}/auth`, {
        method: "POST",
        body: JSON.stringify({ username: login.value, password: secret.value }),
      });
      await refreshAll();
    } catch (problem) {
      error.textContent = problem.message;
    }
  });
  return form;
}

async function forgetDevice(ip) {
  await api(`/api/devices/${ip}/auth`, { method: "DELETE" });
  await refreshAll();
}

export function toggleDevice(ip) {
  if (state.selected === ip) clearPanel();
  else showDevice(ip);
}

export function showDevice(id) {
  const was = state.selected;
  state.selected = id;

  if (was && was !== id) {
    const previous = cy.getElementById(was);
    if (previous.length) sizeNode(previous, 1);
  }

  const node = cy.getElementById(id);
  if (node.length) {
    cy.nodes().unselect();
    node.select();
    sizeNode(node, PICKED_SCALE);
    showPorts(node);
  }

  if (!netOpen) {
    netOpen = true;
    localStorage.setItem("net-open", "yes");
    const net = tree.querySelector(".net");
    if (net) net.classList.add("open");
  }

  applyOpenState();
  const item = tree.querySelector(`[data-ip="${CSS.escape(id)}"]`);
  if (item) item.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

// класс вешаем на готовую строку: пересобранная рождается раскрытой
// и анимации не видно
export function applyOpenState() {
  tree.querySelectorAll(".device").forEach((item) => {
    const open = item.dataset.ip === state.selected;
    item.classList.toggle("open", open);
    item.querySelector(".row").classList.toggle("picked", open);
  });
}

export function clearPanel() {
  const was = state.selected ? cy.getElementById(state.selected) : null;
  state.selected = null;
  if (was && was.length) {
    sizeNode(was, 1);
    was.unselect();
  }
  showPorts(null);
  applyOpenState();
}
