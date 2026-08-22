// групповое применение: слева устройства, справа команды и что из этого вышло

import { api } from "./api.js";
import { refreshAll } from "./load.js";
import { SHEET_FADE } from "./const.js";

const box = document.getElementById("bulk");
const targets = document.getElementById("bulk-targets");
const commands = document.getElementById("bulk-commands");
const results = document.getElementById("bulk-results");
const picked = document.getElementById("bulk-picked");
const send = document.getElementById("bulk-send");

let opened = false;
let hiding = null;
let chosen = new Set();

async function load() {
  targets.textContent = "";
  results.textContent = "";

  const body = await api("/api/apply/targets");
  if (!body.targets.length) {
    const empty = document.createElement("li");
    empty.className = "note";
    empty.textContent =
      "нет устройств, на которые можно отправлять команды: нужен вход на устройство";
    targets.append(empty);
    countPicked();
    return;
  }

  for (const device of body.targets) {
    const item = document.createElement("li");
    const label = document.createElement("label");

    const tick = document.createElement("input");
    tick.type = "checkbox";
    tick.dataset.ip = device.ip;
    tick.checked = chosen.has(device.ip);
    tick.addEventListener("change", () => {
      if (tick.checked) chosen.add(device.ip);
      else chosen.delete(device.ip);
      countPicked();
    });

    const name = document.createElement("span");
    name.className = "name";
    name.textContent = device.hostname;

    const what = document.createElement("span");
    what.className = "note";
    what.textContent = `${device.vendor} ${device.model}`.trim();

    label.append(tick, name, what);
    item.append(label);
    targets.append(item);
  }
  countPicked();
}

function countPicked() {
  const total = targets.querySelectorAll("input[type=checkbox]").length;
  picked.textContent = chosen.size
    ? `выбрано ${chosen.size} из ${total}`
    : "устройства не выбраны";
  send.disabled = chosen.size === 0;
}

export function openBulk() {
  clearTimeout(hiding);
  box.hidden = false;
  requestAnimationFrame(() => box.classList.add("on"));
  opened = true;
  load().catch((error) => {
    results.textContent = error.message;
  });
}

function closeBulk() {
  box.classList.remove("on");
  opened = false;
  hiding = setTimeout(() => {
    box.hidden = true;
  }, SHEET_FADE);
}

function paint(body) {
  results.textContent = "";

  const head = document.createElement("div");
  head.className = "cfg-title";
  head.textContent = `применено на ${body.applied} из ${body.results.length}`;
  results.append(head);

  for (const item of body.results) {
    const line = document.createElement("div");
    line.className = "entry" + (item.ok ? "" : " bad");

    const where = document.createElement("span");
    where.className = "where";
    where.textContent = item.ip;

    const detail = document.createElement("span");
    detail.className = "detail";
    detail.textContent = item.detail;

    line.append(where, detail);
    results.append(line);
  }
}

send.addEventListener("click", async () => {
  send.disabled = true;
  results.textContent = "отправляю";
  try {
    const body = await api("/api/apply", {
      method: "POST",
      body: JSON.stringify({
        ips: [...chosen],
        commands: commands.value,
      }),
    });
    paint(body);
    await refreshAll();
  } catch (error) {
    results.textContent = error.message;
  }
  send.disabled = chosen.size === 0;
});

document.getElementById("bulk-all").addEventListener("click", () => {
  const boxes = [...targets.querySelectorAll("input[type=checkbox]")];
  const turnOn = chosen.size < boxes.length;
  chosen = new Set();
  for (const tick of boxes) {
    tick.checked = turnOn;
    if (turnOn) chosen.add(tick.dataset.ip);
  }
  countPicked();
});

document.getElementById("bulk-open").addEventListener("click", openBulk);
document.getElementById("bulk-close").addEventListener("click", closeBulk);
document.getElementById("bulk-veil").addEventListener("click", closeBulk);
document.addEventListener("keydown", (event) => {
  if (opened && event.key === "Escape") closeBulk();
});
