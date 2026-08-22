// журнал действий, первая вкладка нижней панели. дописывается по мере
// появления записей, отбор идёт по уже загруженному

import { api } from "./api.js";
import { addTab, showTab } from "./dock.js";
import { JOURNAL_EVERY } from "./const.js";

const pane = document.getElementById("journal-pane");
const list = document.getElementById("journal-list");
const find = document.getElementById("journal-find");
const onlyBad = document.getElementById("journal-bad");
const count = document.getElementById("journal-count");

let entries = [];
let last = 0;
let stuckToBottom = true;

addTab({
  id: "journal",
  label: "Журнал",
  closable: false,
  pane,
  onShow: () => {
    if (stuckToBottom) list.scrollTop = list.scrollHeight;
  },
});

export function showJournal() {
  showTab("journal");
}

function when(at) {
  return new Date(at).toLocaleString("ru", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function matches(entry) {
  if (onlyBad.checked && entry.ok) return false;
  const needle = find.value.trim().toLowerCase();
  if (!needle) return true;
  return [entry.word, entry.ip, entry.detail, entry.login]
    .filter(Boolean)
    .some((field) => String(field).toLowerCase().includes(needle));
}

function row(entry) {
  const line = document.createElement("div");
  line.className = "entry" + (entry.ok ? "" : " bad");

  const at = document.createElement("span");
  at.className = "at";
  at.textContent = when(entry.at);

  const who = document.createElement("span");
  who.className = "who";
  who.textContent = entry.login || "продукт";

  const what = document.createElement("span");
  what.className = "what";
  what.textContent = entry.word;

  const where = document.createElement("span");
  where.className = "where";
  where.textContent = entry.ip || "";

  const detail = document.createElement("span");
  detail.className = "detail";
  detail.textContent = entry.detail || "";

  line.append(at, who, what, where, detail);
  return line;
}

function paint() {
  const shown = entries.filter(matches);
  list.textContent = "";
  for (const entry of shown) list.append(row(entry));

  count.textContent = shown.length === entries.length
    ? `${entries.length} записей`
    : `${shown.length} из ${entries.length}`;

  if (stuckToBottom) list.scrollTop = list.scrollHeight;
}

async function pull() {
  let data;
  try {
    data = await api(last ? `/api/journal?after=${last}` : "/api/journal");
  } catch (error) {
    return;
  }
  if (!data.entries.length) return;

  entries = entries.concat(data.entries).slice(-2000);
  last = data.last;
  paint();
}

// у самого низа держим прокрутку, выше по истории не дёргаем
list.addEventListener("scroll", () => {
  stuckToBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 40;
});

find.addEventListener("input", paint);
onlyBad.addEventListener("change", paint);

pull();
setInterval(pull, JOURNAL_EVERY);
