// панель раскрывается, когда человек вошёл в режим конфигурации. сверху
// история версий, снизу текст. черновик показывается до сохранения

import { ICONS } from "./icons.js";
import { api } from "./api.js";
import { state } from "./state.js";
import { statusColor } from "./colors.js";
import { PENDING_EVERY } from "./const.js";

// список устройств перечитывает app.js. прямой импорт замкнул бы круг
// config -> load -> tree -> terminal -> config
function refreshAll() {
  document.dispatchEvent(new CustomEvent("netmap:refresh"));
}

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

const standardWhat = document.getElementById("standard-what");
const standardPick = document.getElementById("standard-pick");
const standardCheck = document.getElementById("standard-check");
const standardName = document.getElementById("standard-name");
const auditList = document.getElementById("audit-list");

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
  await loadStandard();
  await loadAudit();

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

    // на самой свежей откатывать нечего, она и есть текущая
    if (version.restorable && index > 0) {
      const back = document.createElement("button");
      back.className = "link revert";
      back.textContent = "откатить";
      back.title = "Вернуть эту конфигурацию на устройство";
      back.onclick = (event) => {
        event.stopPropagation();
        rollback(version);
      };
      item.appendChild(back);
    }

    versionList.appendChild(item);
  });

  markPicked();
}

async function rollback(version) {
  const name = configName.textContent;
  const sure = confirm(
    `Вернуть на ${name} конфигурацию от ${shortTime(version.at)}?\n\n` +
      "Продукт вернёт прежние значения и удалит настройки, которых в этой версии нет. " +
      "Текущая конфигурация останется в истории, откатиться обратно можно."
  );
  if (!sure) return;

  setWhat("откат идёт", false);
  try {
    const done = await api(
      `/api/devices/${configIp}/versions/${version.id}/rollback`,
      { method: "POST" }
    );
    await loadVersions();
    if (done.ok) {
      await showLatest();
    } else {
      setWhat(`откат не завершён: ${done.detail}`, true);
      paint(done.left || done.detail, true);
    }
    await loadStandard();
    await loadAudit();
    await refreshAll();
  } catch (error) {
    setWhat(`откат не удался: ${error.message}`, false);
  }
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

async function loadStandard() {
  if (!configIp) return;

  const [drift, all] = await Promise.all([
    api(`/api/baselines/devices/${configIp}`),
    api("/api/baselines"),
  ]);

  const device = state.devices.find((item) => item.ip === configIp);
  const vendor = device?.vendor || "";

  standardPick.textContent = "";
  const none = document.createElement("option");
  none.value = "";
  none.textContent = "не назначен";
  standardPick.append(none);

  for (const model of all.baselines) {
    // эталон одного вендора на железо другого не ложится
    if (vendor && model.vendor && model.vendor !== vendor) continue;
    const option = document.createElement("option");
    option.value = model.id;
    option.textContent = `${model.name} (${model.devices})`;
    standardPick.append(option);
  }
  standardPick.value = drift.baseline ? String(drift.baseline.id) : "";

  standardCheck.hidden = !drift.baseline;
  if (!drift.baseline) {
    standardWhat.textContent =
      "Эталон не назначен. Пока его нет, расхождения не отслеживаются.";
    standardWhat.className = "note";
    return;
  }
  if (drift.state === "match") {
    standardWhat.textContent = `Совпадает с эталоном «${drift.baseline.name}».`;
    standardWhat.className = "note good";
  } else if (drift.state === "differs") {
    const rows = (drift.diff || "").split("\n").length;
    standardWhat.textContent =
      `Расходится с эталоном «${drift.baseline.name}», ${rows} строк различий.`;
    standardWhat.className = "note bad";
  } else {
    standardWhat.textContent = "Конфигурация ещё не снята, сверять не с чем.";
    standardWhat.className = "note";
  }
}

async function loadAudit() {
  if (!configIp) return;
  auditList.textContent = "";

  let body;
  try {
    body = await api(`/api/devices/${configIp}/checks`);
  } catch (error) {
    return;
  }

  for (const item of body.checks) {
    const row = document.createElement("li");
    row.className = `audit ${item.state}`;

    const mark = document.createElement("span");
    mark.className = "mark";
    mark.textContent = item.state === "pass" ? "✓" : item.state === "fail" ? "✕" : "—";

    const title = document.createElement("span");
    title.className = "name";
    title.textContent = item.title || item.code;
    title.title = item.why || "";

    row.append(mark, title);

    if (item.detail) {
      const why = document.createElement("span");
      why.className = "note";
      why.textContent = item.detail;
      row.append(why);
    }
    auditList.append(row);
  }
}

standardCheck.onclick = async () => {
  const drift = await api(`/api/baselines/devices/${configIp}`);
  if (!drift.diff) {
    setWhat("Совпадает с эталоном", true);
    paint("расхождений нет", false);
    return;
  }
  setWhat("Расхождение с эталоном", true);
  paint(drift.diff, true);
};

document.getElementById("standard-attach").onclick = async () => {
  const picked = standardPick.value;
  try {
    if (picked) {
      await api(`/api/baselines/${picked}/devices`, {
        method: "POST",
        body: JSON.stringify({ ips: [configIp] }),
      });
    } else {
      await api(`/api/baselines/devices/${configIp}`, { method: "DELETE" });
    }
    await loadStandard();
    await refreshAll();
  } catch (error) {
    standardWhat.textContent = error.message;
    standardWhat.className = "note bad";
  }
};

document.getElementById("standard-make").onsubmit = async (event) => {
  event.preventDefault();
  const versionId = pickedVersion || configHistory[0]?.id;
  if (!versionId) return;

  try {
    await api("/api/baselines", {
      method: "POST",
      body: JSON.stringify({ name: standardName.value, version_id: versionId }),
    });
    standardName.value = "";
    await loadStandard();
  } catch (error) {
    standardWhat.textContent = error.message;
    standardWhat.className = "note bad";
  }
};

document.getElementById("audit-again").onclick = async () => {
  const box = document.getElementById("audit");
  box.classList.add("busy");
  try {
    await api(`/api/devices/${configIp}/checks`, { method: "POST" });
    await loadAudit();
    await refreshAll();
  } finally {
    box.classList.remove("busy");
  }
};

configClose.onclick = closeConfig;
backCurrent.onclick = showLatest;
