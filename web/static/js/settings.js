// окно настроек: разделы слева, содержимое справа, фон под ним размывается

import { api } from "./api.js";
import { state } from "./state.js";
import { applyTheme, themeChoice } from "./theme.js";
import { renderList } from "./tree.js";
import { SHEET_FADE } from "./const.js";

const sheet = document.getElementById("settings");
const problem = document.getElementById("sheet-problem");
const tabs = [...document.querySelectorAll("#sheet .tab")];
const panes = [...document.querySelectorAll("#sheet .pane")];

const subnetForm = document.getElementById("subnet-form");
const subnet = document.getElementById("subnet");
const lldp = document.getElementById("lldp");
const keep = document.getElementById("keep");
const keepNote = document.getElementById("keep-note");
const keepForm = document.getElementById("keep-form");
const keepWhy = document.getElementById("keep-why");
const keepPassword = document.getElementById("keep-password");
const recovery = document.getElementById("recovery");
const passwordForm = document.getElementById("password-form");

const KEEPING = {
  yes: "Пароли устройств лежат в базе зашифрованными. После перезапуска "
    + "достаточно одного входа в продукт, и всё оборудование снова доступно.",
  no: "Пароли устройств живут только в памяти. На диск не попадают, но после "
    + "перезапуска войти придётся на каждое устройство заново.",
};

let opened = false;
let hiding = null;

function say(text, bad = false) {
  problem.textContent = text;
  problem.classList.toggle("bad", bad);
}

function toggle(button, on) {
  button.setAttribute("aria-checked", on ? "true" : "false");
}

function checked(button) {
  return button.getAttribute("aria-checked") === "true";
}

async function load() {
  const body = await api("/api/settings");

  document.getElementById("account-name").textContent = body.login || "";
  document.getElementById("account-role").textContent =
    body.role === "admin" ? "администратор" : body.role || "";
  showAccount(body);

  subnet.value = body.subnet;
  state.subnet = body.subnet;
  toggle(lldp, body.lldp_auto);
  toggle(keep, body.keep_credentials);
  keepNote.textContent = body.keep_credentials ? KEEPING.yes : KEEPING.no;

  markTheme(themeChoice());
}

function markTheme(choice) {
  document.querySelectorAll("#theme-pick button").forEach((button) => {
    button.classList.toggle("on", button.dataset.theme === choice);
  });
}

export function openSettings() {
  clearTimeout(hiding);
  sheet.hidden = false;
  // без отдельного кадра переход не начнётся: элемент только что показался
  requestAnimationFrame(() => sheet.classList.add("on"));
  opened = true;
  say("");
  recovery.hidden = true;
  keepForm.hidden = true;
  load().catch((error) => say(error.message, true));
}

function closeSettings() {
  sheet.classList.remove("on");
  opened = false;
  keepPassword.value = "";
  hiding = setTimeout(() => {
    sheet.hidden = true;
  }, SHEET_FADE);
}

function show(name) {
  say("");
  tabs.forEach((tab) => tab.classList.toggle("on", tab.dataset.pane === name));
  panes.forEach((pane) => pane.classList.toggle("on", pane.dataset.pane === name));
}

tabs.forEach((tab) => tab.addEventListener("click", () => show(tab.dataset.pane)));

document.getElementById("account").addEventListener("click", openSettings);
document.getElementById("sheet-close").addEventListener("click", closeSettings);
document.getElementById("settings-veil").addEventListener("click", closeSettings);
document.addEventListener("keydown", (event) => {
  if (opened && event.key === "Escape") closeSettings();
});

document.querySelectorAll("#theme-pick button").forEach((button) => {
  button.addEventListener("click", () => {
    applyTheme(button.dataset.theme);
    markTheme(button.dataset.theme);
  });
});

subnetForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  say("");
  try {
    const body = await api("/api/settings/subnet", {
      method: "POST",
      body: JSON.stringify({ subnet: subnet.value }),
    });
    state.subnet = body.subnet;
    renderList();
    say("сеть сохранена, обход начался");
  } catch (error) {
    say(error.message, true);
  }
});

lldp.addEventListener("click", async () => {
  const next = !checked(lldp);
  toggle(lldp, next);
  try {
    await api("/api/settings/lldp", {
      method: "POST",
      body: JSON.stringify({ auto: next }),
    });
    say(next ? "продукт будет включать LLDP сам" : "LLDP включает администратор");
  } catch (error) {
    toggle(lldp, !next);
    say(error.message, true);
  }
});

// режим хранения меняется только с паролем: без него не завернуть ключ
keep.addEventListener("click", () => {
  const next = !checked(keep);
  keepForm.hidden = false;
  recovery.hidden = true;
  keepWhy.textContent = next
    ? "Включение зашифрует доступы, которые уже введены, и выдаст ключ восстановления."
    : "Выключение сотрёт с диска и доступы, и ключ восстановления. Введённое "
      + "останется в памяти до перезапуска.";
  keepPassword.focus();
  say("");
});

keepForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const next = !checked(keep);
  try {
    const body = await api("/api/settings/credentials", {
      method: "POST",
      body: JSON.stringify({ keep: next, password: keepPassword.value }),
    });
    toggle(keep, body.keep);
    keepNote.textContent = body.keep ? KEEPING.yes : KEEPING.no;
    keepForm.hidden = true;
    keepPassword.value = "";
    if (body.recovery) {
      document.getElementById("recovery-key").textContent = body.recovery;
      recovery.hidden = false;
    }
    say(body.keep ? "доступы теперь хранятся" : "доступы больше не хранятся");
  } catch (error) {
    say(error.message, true);
  }
});

passwordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const now = document.getElementById("password-now");
  const fresh = document.getElementById("password-new");
  try {
    await api("/api/settings/password", {
      method: "POST",
      body: JSON.stringify({ current: now.value, following: fresh.value }),
    });
    now.value = "";
    fresh.value = "";
    say("пароль изменён");
  } catch (error) {
    say(error.message, true);
  }
});

const backupSaid = document.getElementById("backup-said");

document.getElementById("backup-save").addEventListener("click", async () => {
  backupSaid.textContent = "собираю копию";
  try {
    const response = await fetch("/api/backup/export");
    if (!response.ok) throw new Error("выгрузка не удалась");

    const blob = await response.blob();
    const name = (response.headers.get("Content-Disposition") || "")
      .match(/filename="([^"]+)"/)?.[1] || "netmap.json.gz";

    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = name;
    link.click();
    URL.revokeObjectURL(link.href);
    backupSaid.textContent = `${name}, ${Math.round(blob.size / 1024)} КБ`;
  } catch (error) {
    backupSaid.textContent = error.message;
  }
});

document.getElementById("backup-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const picked = document.getElementById("backup-file").files[0];
  if (!picked) {
    backupSaid.textContent = "файл не выбран";
    return;
  }

  backupSaid.textContent = "читаю копию";
  try {
    // файл уходит телом запроса как есть, разбирает его сервер
    const response = await fetch("/api/backup/import", {
      method: "POST",
      body: picked,
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "восстановление не удалось");
    backupSaid.textContent =
      `добавлено версий ${body.configs}, эталонов ${body.baselines}, ` +
      `пропущено совпадающих ${body.skipped}`;
  } catch (error) {
    backupSaid.textContent = error.message;
  }
});

document.getElementById("leave").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  location.href = "/";
});

export function showAccount(body) {
  document.getElementById("account-login").textContent = body.login || "";
  document.getElementById("account-letter").textContent = (body.login || "?")[0];
}
