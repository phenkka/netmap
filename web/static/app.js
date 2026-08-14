function statusColor(status) {
  return themeColor(status === "authorized" ? "--pos" : "--neg");
}

function themeColor(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

const NOTES = {
  authorized: "авторизовано",
  detected: "нет доступа",
  failed: "ошибка входа",
  not_network: "не сетевое устройство",
};

const ICON_SIZE = 140;
const NODE_FONT = 14;
const PORT_FONT = 12;
// отступ считается от края значка, а не от центра
const PORT_OFFSET = 55;
// по углам значка пустота, считать её занятой нельзя
const ICON_BODY = 0.72;
const GAP = 10;
const HOVER_SCALE = 1.16;
const PICKED_SCALE = 1.08;
const MOTION = 420;
const EASING = "ease-in-out";

let devices = [];
let selected = null;
let rootId = localStorage.getItem("root") || null;

const cy = cytoscape({
  container: document.getElementById("map"),
  minZoom: 0.3,
  maxZoom: 3,
  style: [
    {
      selector: "node",
      style: {
        "background-opacity": 0,
        "border-width": 0,
        "overlay-opacity": 0,
        "background-image": (n) =>
          (ICONS[n.data("type")] || ICONS.unknown)(statusColor(n.data("status"))),
        "background-fit": "contain",
        "background-width": "100%",
        "background-height": "100%",
        width: ICON_SIZE,
        height: ICON_SIZE,
        label: "data(label)",
        color: () => themeColor("--text"),
        "font-size": NODE_FONT,
        "text-wrap": "wrap",
        "text-justification": "center",
        "text-events": "no",
      },
    },
    {
      selector: "edge",
      style: {
        width: 2,
        "line-color": () => themeColor("--border"),
        "curve-style": "bezier",
        "source-text-offset": PORT_OFFSET,
        "target-text-offset": PORT_OFFSET,
        "font-size": PORT_FONT,
        color: () => themeColor("--muted"),
        "text-background-color": () => themeColor("--bg"),
        "text-background-opacity": 0.85,
        "text-background-padding": 3,
        "text-background-shape": "roundrectangle",
      },
    },
    {
      selector: "edge.ports",
      style: {
        "line-color": () => themeColor("--accent"),
        color: () => themeColor("--text"),
        "z-index": 10,
      },
    },
  ],
});

// неавторизованные моргают: связей у них нет, пока не введён пароль
let bright = true;
setInterval(() => {
  bright = !bright;
  cy.nodes().forEach((node) => {
    const dim = node.data("status") !== "authorized";
    node.style("opacity", dim && !bright ? 0.35 : 1);
  });
}, 600);

// --- подписи ------------------------------------------------------------
// каждая подпись считается прямоугольником на экране. имя устройства
// переезжает на свободную сторону, подпись порта без места не рисуется

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

function layoutLabels() {
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

// --- отмена -------------------------------------------------------------
// отменяются перетаскивание и перестройка схемы

const HISTORY_DEPTH = 50;
const history = [];
const future = [];
let beforeDrag = null;

function snapshot() {
  const places = {};
  cy.nodes().forEach((node) => {
    places[node.id()] = { ...node.position() };
  });
  return places;
}

function remember(before) {
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
  setTimeout(layoutLabels, MOTION + 20);
}

function undo() {
  if (history.length === 0) return;
  future.push(snapshot());
  restore(history.pop());
  setStatus("действие отменено");
}

function redo() {
  if (future.length === 0) return;
  history.push(snapshot());
  restore(future.pop());
  setStatus("действие возвращено");
}

cy.on("grab", "node", () => {
  beforeDrag = snapshot();
});
cy.on("dragfree", "node", () => {
  if (beforeDrag) remember(beforeDrag);
  beforeDrag = null;
});

document.addEventListener("keydown", (event) => {
  const typing = ["INPUT", "TEXTAREA"].includes(event.target.tagName);
  if (typing || !(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "z") {
    return;
  }
  event.preventDefault();
  if (event.shiftKey) redo();
  else undo();
});

// --- память вида --------------------------------------------------------
// расставленную схему делают один раз, она переживает перезагрузку

const VIEW_KEY = "netmap-view";
const PLACES_KEY = "netmap-places";

function savePlaces() {
  try {
    localStorage.setItem(PLACES_KEY, JSON.stringify(snapshot()));
  } catch (error) {
    /* инкогнито, схема просто не запомнится */
  }
}

function savedPlaces() {
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

function restoreView() {
  try {
    const view = JSON.parse(localStorage.getItem(VIEW_KEY) || "null");
    if (!view || !view.zoom) return false;
    cy.viewport({ zoom: view.zoom, pan: view.pan });
    return true;
  } catch (error) {
    return false;
  }
}

cy.on("zoom pan", saveView);
cy.on("dragfree", "node", savePlaces);

let pending = null;
function scheduleLabels() {
  if (pending) return;
  pending = requestAnimationFrame(() => {
    pending = null;
    layoutLabels();
  });
}

cy.on("position", "node", scheduleLabels);
cy.on("zoom pan", scheduleLabels);

// --- фон и тема ---------------------------------------------------------
// клетка двигается и масштабируется вместе со схемой

const mapBox = document.getElementById("map");

function syncGrid() {
  const zoom = cy.zoom();
  const pan = cy.pan();
  const small = 32 * zoom;
  const big = 160 * zoom;
  mapBox.style.backgroundSize =
    `${big}px ${big}px, ${big}px ${big}px, ${small}px ${small}px, ${small}px ${small}px`;
  mapBox.style.backgroundPosition = `${pan.x}px ${pan.y}px`;
}

cy.on("zoom pan", syncGrid);

const themeButton = document.getElementById("theme");

const THEME_FADE = 200;

function applyTheme(light) {
  const root = document.documentElement;
  if (light) root.setAttribute("data-theme", "light");
  else root.removeAttribute("data-theme");

  themeButton.title = light ? "Включить тёмную тему" : "Включить светлую тему";
  try {
    localStorage.setItem("netmap-theme", light ? "light" : "dark");
  } catch (error) {
    /* режим инкогнито, тема просто не запомнится */
  }

  // холст перерисовываем несколько раз, чтобы не отставал от панелей
  fadeTerminals(light);

  const started = Date.now();
  const timer = setInterval(() => {
    cy.style().update();
    if (Date.now() - started > THEME_FADE) clearInterval(timer);
  }, 40);
}

themeButton.addEventListener("click", () =>
  applyTheme(document.documentElement.getAttribute("data-theme") !== "light")
);

syncGrid();

// --- сервер -------------------------------------------------------------

async function api(path, options) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || "ошибка запроса");
  return body;
}

function setStatus(text) {
  document.getElementById("status").textContent = text;
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
  if (rootId && cy.getElementById(rootId).length) return rootId;
  let best = null;
  cy.nodes().forEach((node) => {
    if (!best || node.degree() > best.degree()) best = node;
  });
  return best ? best.id() : null;
}

function fitView(smooth = false) {
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

function relayout({ track = true, smooth = true, fit = true } = {}) {
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
async function loadGraph() {
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
  for (const link of graph.edges) {
    liveEdges.add(link.id);
    const data = {
      ...link,
      source_short: shortPort(link.source_port),
      target_short: shortPort(link.target_port),
    };
    const known = cy.getElementById(link.id);
    if (known.length) known.data(data);
    else cy.add({ group: "edges", data });
  }

  cy.nodes().forEach((node) => {
    if (!liveNodes.has(node.id())) node.remove();
  });
  cy.edges().forEach((link) => {
    if (!liveEdges.has(link.id())) link.remove();
  });

  if (appeared > 0) {
    relayout({ track: false, smooth: had });
  } else {
    if (!had) restoreView();
    layoutLabels();
  }
}

let lastDevices = "";

async function loadDevices() {
  devices = (await api("/api/devices")).devices;

  // перерисовка списка сбрасывает наведение и выделение, поэтому делаем её
  // только когда данные действительно поменялись
  const signature = JSON.stringify(devices);
  if (signature === lastDevices) return;
  lastDevices = signature;
  renderList();
  applyOpenState();
}

// --- карта --------------------------------------------------------------

function showPorts(node) {
  cy.edges().removeClass("ports");
  if (node) node.connectedEdges().addClass("ports");
  layoutLabels();
}

function sizeNode(node, scale) {
  if (!node || !node.length) return;
  node.stop();
  node.animate(
    { style: { width: ICON_SIZE * scale, height: ICON_SIZE * scale } },
    { duration: 150, easing: "ease-out", step: scheduleLabels }
  );
}

function restoreSize(node) {
  sizeNode(node, node.id() === selected ? PICKED_SCALE : 1);
}

// двойного клика у карты нет, считаем два нажатия подряд
const DOUBLE_TAP = 350;
let lastTap = { id: null, at: 0 };

cy.on("tap", "node", (event) => {
  const node = event.target;
  const id = node.id();
  const now = Date.now();

  if (lastTap.id === id && now - lastTap.at < DOUBLE_TAP) {
    lastTap = { id: null, at: 0 };
    const device = devices.find((d) => d.ip === id);
    if (device && device.authorized) {
      openTerminal(device.ip, device.hostname || device.ip);
    } else {
      setStatus("терминал открывается только у авторизованного устройства");
    }
    return;
  }

  lastTap = { id, at: now };
  showDevice(id);
});

cy.on("mouseover", "node", (event) => {
  cy.container().style.cursor = "pointer";
  sizeNode(event.target, HOVER_SCALE);
  showPorts(event.target);
});

cy.on("mouseout", "node", (event) => {
  cy.container().style.cursor = "";
  restoreSize(event.target);
  const chosen = selected ? cy.getElementById(selected) : null;
  showPorts(chosen && chosen.length ? chosen : null);
});

cy.on("tap", (event) => {
  if (event.target === cy) clearPanel();
});

// --- дерево сети --------------------------------------------------------
// корень это сеть, внутри устройства со значком своего типа. раскрытое
// устройство выделяется на карте, и наоборот

const tree = document.getElementById("tree");
let netOpen = localStorage.getItem("net-open") !== "no";

const CARET =
  '<svg class="caret" viewBox="0 0 12 12" fill="none" stroke="currentColor" ' +
  'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' +
  '<path d="M4.5 2.5 8 6l-3.5 3.5"/></svg>';

function renderList() {
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
  count.textContent = devices.length || "";

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

  for (const device of devices) {
    items.append(deviceRow(device));
  }

  inner.append(items);
  fold.append(inner);
  net.append(head, fold);
  tree.append(net);
}

function deviceRow(device) {
  const item = document.createElement("li");
  item.className = "device" + (device.ip === selected ? " open" : "");
  item.dataset.ip = device.ip;

  const row = document.createElement("button");
  row.className = "row" + (device.ip === selected ? " picked" : "");

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

  const list = document.createElement("dl");
  list.append(
    ...field("Адрес", device.ip),
    ...field("MAC", device.mac || "нет данных"),
    ...field("Производитель", device.vendor || device.vendor_guess || "не определён")
  );
  if (device.model) list.append(...field("Модель", device.model));
  if (device.version) list.append(...field("Версия", device.version));
  box.append(list);

  box.append(
    button("Сделать корнем схемы", "secondary", () => {
      rootId = device.ip;
      localStorage.setItem("root", rootId);
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

function toggleDevice(ip) {
  if (selected === ip) clearPanel();
  else showDevice(ip);
}

function showDevice(id) {
  const was = selected;
  selected = id;

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
function applyOpenState() {
  tree.querySelectorAll(".device").forEach((item) => {
    const open = item.dataset.ip === selected;
    item.classList.toggle("open", open);
    item.querySelector(".row").classList.toggle("picked", open);
  });
}

function clearPanel() {
  const was = selected ? cy.getElementById(selected) : null;
  selected = null;
  if (was && was.length) {
    sizeNode(was, 1);
    was.unselect();
  }
  showPorts(null);
  applyOpenState();
}

async function refreshAll() {
  await loadDevices();
  await loadGraph();
}

// --- обновление ---------------------------------------------------------
// обход сети ведёт сервер в фоне, страница только читает найденное

const REFRESH_EVERY = 3000;

async function firstScan() {
  try {
    await api("/api/scan", {
      method: "POST",
      body: JSON.stringify({ subnet: document.getElementById("subnet").value.trim() }),
    });
  } catch (error) {
    setStatus(error.message);
  }
  await refreshAll();
}

setInterval(refreshAll, REFRESH_EVERY);
refreshAll();
firstScan();

// --- терминал -----------------------------------------------------------
// SSH-сессия с псевдотерминалом. пароль в браузер не приходит, сервер
// берёт его из своей памяти. у каждой вкладки своё соединение

const termBox = document.getElementById("terminal");
const termBody = document.getElementById("term-body");
const termList = document.getElementById("term-list");

const sessions = new Map();
let active = null;

// фон прозрачный, сквозь него видно панель, а она меняется плавно
const TERM_DARK = {
  background: "#00000000",
  foreground: "#f9fafb",
  cursor: "#f9fafb",
  selectionBackground: "rgba(22,82,240,0.4)",
};

const TERM_LIGHT = {
  background: "#00000000",
  foreground: "#0f1419",
  cursor: "#0f1419",
  selectionBackground: "rgba(22,82,240,0.25)",
};

function termTheme() {
  return document.documentElement.getAttribute("data-theme") === "light"
    ? TERM_LIGHT
    : TERM_DARK;
}

// текст рисуется на холсте, css его не анимирует, переливаем цвет сами
function mixColor(from, to, part) {
  const parse = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const a = parse(from);
  const b = parse(to);
  const channel = (i) => Math.round(a[i] + (b[i] - a[i]) * part);
  return (
    "#" +
    [0, 1, 2]
      .map((i) => channel(i).toString(16).padStart(2, "0"))
      .join("")
  );
}

function fadeTerminals(light) {
  if (sessions.size === 0) return;
  const from = light ? TERM_DARK : TERM_LIGHT;
  const to = light ? TERM_LIGHT : TERM_DARK;
  const started = performance.now();

  const step = (now) => {
    const part = Math.min((now - started) / THEME_FADE, 1);
    const colour = mixColor(from.foreground, to.foreground, part);
    for (const session of sessions.values()) {
      session.term.options.theme = { ...to, foreground: colour, cursor: colour };
    }
    if (part < 1) requestAnimationFrame(step);
  };

  requestAnimationFrame(step);
}

function openTerminal(ip, name) {
  termBox.hidden = false;
  if (!sessions.has(ip)) createSession(ip, name);
  showSession(ip);
  cy.resize();
  layoutLabels();
}

function createSession(ip, name) {
  const pane = document.createElement("div");
  pane.className = "term-pane";
  pane.hidden = true;
  termBody.append(pane);

  const term = new Terminal({
    fontFamily: 'ui-monospace, Menlo, Consolas, "Courier New", monospace',
    fontSize: 13,
    cursorBlink: true,
    scrollback: 5000,
    allowTransparency: true,
    theme: termTheme(),
  });
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  term.open(pane);

  const session = { ip, name, term, fit, pane, socket: null, state: "wait" };
  sessions.set(ip, session);

  term.onData((data) => send(session, { type: "input", data }));
  term.onResize(({ cols, rows }) => send(session, { type: "size", cols, rows }));

  connect(session);
  return session;
}

function connect(session) {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(
    `${protocol}://${location.host}/api/devices/${session.ip}/terminal`
  );
  session.socket = socket;

  socket.onopen = () => {
    session.state = "online";
    renderTabs();
    send(session, { type: "size", cols: session.term.cols, rows: session.term.rows });
  };
  socket.onmessage = (event) => session.term.write(event.data);
  socket.onclose = () => {
    session.state = "offline";
    renderTabs();
    session.term.write("\r\n\x1b[2m— сессия закрыта —\x1b[0m\r\n");
  };
  socket.onerror = () => {
    session.state = "offline";
    renderTabs();
  };
}

function send(session, message) {
  if (session.socket && session.socket.readyState === WebSocket.OPEN) {
    session.socket.send(JSON.stringify(message));
  }
}

function showSession(ip) {
  active = ip;
  for (const session of sessions.values()) {
    session.pane.hidden = session.ip !== ip;
  }
  renderTabs();

  const session = sessions.get(ip);
  if (!session) return;
  fitSession(session);
  session.term.focus();
}

function fitSession(session) {
  if (!session || session.pane.hidden || termBox.hidden) return;
  try {
    session.fit.fit();
  } catch (error) {
    /* размеры ещё не устоялись */
  }
}

function closeSession(ip) {
  const session = sessions.get(ip);
  if (!session) return;

  if (session.socket) {
    session.socket.onclose = null;
    session.socket.close();
  }
  session.term.dispose();
  session.pane.remove();
  sessions.delete(ip);

  const next = sessions.keys().next();
  if (next.done) {
    termBox.hidden = true;
    active = null;
    renderTabs();
  } else {
    showSession(next.value);
  }
  cy.resize();
  layoutLabels();
}

function renderTabs() {
  termList.textContent = "";
  for (const session of sessions.values()) {
    const tab = document.createElement("button");
    tab.className = "term-tab " + session.state;
    if (session.ip === active) tab.classList.add("active");

    const live = document.createElement("i");
    live.className = "live";

    const name = document.createElement("span");
    name.textContent = session.name;

    const shut = document.createElement("span");
    shut.className = "shut";
    shut.textContent = "✕";
    shut.title = "Закрыть сессию";
    shut.addEventListener("click", (event) => {
      event.stopPropagation();
      closeSession(session.ip);
    });

    tab.append(live, name, shut);
    tab.addEventListener("click", () => showSession(session.ip));
    termList.append(tab);
  }
}

// крестик справа прячет панель, сессии остаются живыми
document.getElementById("term-hide").addEventListener("click", () => {
  termBox.hidden = true;
  cy.resize();
  layoutLabels();
});

document.getElementById("term-grip").addEventListener("mousedown", (event) => {
  event.preventDefault();
  const startY = event.clientY;
  const startHeight = termBox.offsetHeight;

  const move = (moveEvent) => {
    const height = Math.min(
      Math.max(startHeight + startY - moveEvent.clientY, 120),
      window.innerHeight - 220
    );
    termBox.style.height = `${height}px`;
    cy.resize();
    fitSession(sessions.get(active));
  };
  const stop = () => {
    document.removeEventListener("mousemove", move);
    document.removeEventListener("mouseup", stop);
    layoutLabels();
  };

  document.addEventListener("mousemove", move);
  document.addEventListener("mouseup", stop);
});

window.addEventListener("resize", () => {
  cy.resize();
  fitSession(sessions.get(active));
  layoutLabels();
});
