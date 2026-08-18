// панель раскрывается, когда человек вошёл в режим конфигурации. сверху
// история версий, снизу текст. черновик показывается до сохранения

import { ICONS } from "./icons.js";
import { api } from "./api.js";
import { state } from "./state.js";
import { statusColor } from "./colors.js";
import { PENDING_EVERY } from "./const.js";

const panel = document.getElementById("panel");
const configName = document.getElementById("config-name");
const configIcon = document.getElementById("config-icon");
const configText = document.getElementById("config-text");
const configWhat = document.getElementById("config-what");
const backCurrent = document.getElementById("back-current");
const versionList = document.getElementById("version-list");
const pendingMark = document.getElementById("pending-mark");
const configClose = document.getElementById("config-close");
const configLock = document.getElementById("config-lock");

let configIp = null;
let pendingTimer = null;
let pickedVersion = null;
let configHistory = [];

export function shownIp() {
  return configIp;
}

export function lockConfig(locked) {
  configClose.hidden = locked;
  configLock.hidden = !locked;
}

export async function openConfig(ip, locked = false) {
  lockConfig(locked);
  const device = state.devices.find((item) => item.ip === ip);
  configName.textContent = device?.hostname || ip;
  configIcon.src = (ICONS[device?.type] || ICONS.unknown)(statusColor(device?.state));
  configIp = ip;
  pickedVersion = null;
  panel.classList.add("config");

  await loadVersions();
  await showLatest();

  clearInterval(pendingTimer);
  pendingTimer = setInterval(loadPending, PENDING_EVERY);
  loadPending();
}

export function closeConfig() {
  configIp = null;
  pickedVersion = null;
  panel.classList.remove("config");
  pendingMark.hidden = true;
  lockConfig(false);
  clearInterval(pendingTimer);
  pendingTimer = null;
}

export async function loadVersions() {
  if (!configIp) return;
  configHistory = (await api(`/api/devices/${configIp}/versions`)).versions;
  versionList.innerHTML = "";

  if (!configHistory.length) {
    const empty = document.createElement("li");
    empty.className = "version when";
    empty.textContent = "версий пока нет";
    versionList.appendChild(empty);
    return;
  }

  configHistory.forEach((version, index) => {
    const older = configHistory[index + 1];
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.className = "version";
    button.dataset.id = version.id;

    const when = document.createElement("span");
    when.className = "when";
    when.textContent = shortTime(version.at);

    const what = document.createElement("span");
    if (older) {
      const delta = version.lines - older.lines;
      what.className = delta < 0 ? "shrank" : "grew";
      what.textContent = delta === 0 ? "правка" : `${delta > 0 ? "+" : ""}${delta} строк`;
    } else {
      what.className = "when";
      what.textContent = "первый снимок";
    }

    button.append(when, what);
    button.onclick = () => showVersion(index);
    item.appendChild(button);
    versionList.appendChild(item);
  });

  markPicked();
}

function shortTime(at) {
  return new Date(at).toLocaleString("ru", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

function markPicked() {
  versionList.querySelectorAll(".version").forEach((button) => {
    button.classList.toggle("picked", Number(button.dataset.id) === pickedVersion);
  });
}

function setWhat(text, canReturn) {
  configWhat.textContent = text;
  backCurrent.hidden = !canReturn;
}

async function showLatest() {
  pickedVersion = null;
  markPicked();
  setWhat("Текущая конфигурация", false);

  if (!configHistory.length) {
    configText.textContent = "конфигурация ещё не снята";
    return;
  }
  const latest = await api(`/api/devices/${configIp}/versions/${configHistory[0].id}`);
  paint(latest.text, false);
}

async function showVersion(index) {
  const version = configHistory[index];
  const older = configHistory[index + 1];
  pickedVersion = version.id;
  markPicked();

  // соседняя версия не обязательно id-1, номера сквозные по всем устройствам
  if (!older) {
    setWhat(`Первый снимок, ${shortTime(version.at)}`, true);
    const first = await api(`/api/devices/${configIp}/versions/${version.id}`);
    paint(first.text, false);
    return;
  }

  // одиночная версия сама по себе мало говорит, показываем что в ней изменилось
  setWhat(`Изменение ${shortTime(version.at)}`, true);
  const data = await api(`/api/devices/${configIp}/diff?a=${older.id}&b=${version.id}`);
  paint(data.diff, true);
}

async function loadPending() {
  if (!configIp) return;
  let data;
  try {
    data = await api(`/api/devices/${configIp}/pending`);
  } catch (error) {
    return;
  }

  const had = !pendingMark.hidden;
  pendingMark.hidden = !data.diff;

  if (data.diff) {
    // не перебиваем то, что человек сам открыл из истории
    if (!pickedVersion) {
      setWhat("Несохранённая правка", false);
      paint(data.diff, true);
    }
  } else if (had) {
    // черновик опустел, значит правку сохранили, снимаем новую версию
    await api(`/api/devices/${configIp}/config`, { method: "POST" });
    await loadVersions();
    await showLatest();
  }
}

function paint(text, asDiff) {
  configText.textContent = "";
  // в разнице свои номера, в заголовках кусков
  configText.classList.toggle("numbered", !asDiff);
  for (const line of text.split("\n")) {
    const row = document.createElement("span");
    if (asDiff) {
      // заголовки проверяем первыми, иначе +++ и --- сойдут за правку
      if (line.startsWith("@@") || line.startsWith("---") || line.startsWith("+++")) {
        row.className = "at";
      } else if (line.startsWith("+")) row.className = "add";
      else if (line.startsWith("-")) row.className = "drop";
    }
    row.textContent = `${line}\n`;
    configText.appendChild(row);
  }
}

configClose.onclick = closeConfig;
backCurrent.onclick = showLatest;
