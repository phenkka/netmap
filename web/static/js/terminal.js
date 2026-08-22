// SSH-сессия с псевдотерминалом. пароль в браузер не приходит, сервер
// берёт его из своей памяти. у каждой вкладки своё соединение

import { api } from "./api.js";
import { cy } from "./cy.js";
import { mixColor } from "./colors.js";
import { focusNode } from "./map.js";
import { layoutLabels } from "./labels.js";
import { closeConfig, loadVersions, lockConfig, openConfig, shownIp } from "./config.js";
import { addTab, markTab, openDock, paneFor, removeTab, showTab } from "./dock.js";
import { THEME_FADE } from "./const.js";

const sessions = new Map();

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

export function fadeTerminals(light) {
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

export function openTerminal(ip, name) {
  if (!sessions.has(ip)) createSession(ip, name);
  openDock(tabId(ip));
  showTab(tabId(ip));
  cy.resize();
  layoutLabels();

  // панель закрывает низ карты, устройство иначе остаётся под ней
  const node = cy.getElementById(ip);
  if (node.length) focusNode(node);
}

function tabId(ip) {
  return `term:${ip}`;
}

function createSession(ip, name) {
  const pane = paneFor(tabId(ip));

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

  addTab({
    id: tabId(ip),
    label: name,
    pane,
    state: "wait",
    onShow: () => {
      fitSession(session);
      term.focus();
    },
    onResize: () => fitSession(session),
    onClose: () => shutSession(session),
  });

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
    markTab(tabId(session.ip), "online");
    send(session, { type: "size", cols: session.term.cols, rows: session.term.rows });
  };

  // поток идёт байтами, служебные сообщения текстом
  socket.binaryType = "arraybuffer";
  socket.onmessage = (event) => {
    if (typeof event.data !== "string") {
      session.term.write(new Uint8Array(event.data));
      return;
    }
    const notice = JSON.parse(event.data);
    if (notice.type === "config_mode") {
      openConfig(session.ip, true);
    } else if (notice.type === "config_exit") {
      // правку могли сохранить перед выходом, снимаем версию вдогонку
      api(`/api/devices/${session.ip}/config`, { method: "POST" }).catch(() => {});
      closeConfig();
    } else if (notice.type === "error") {
      session.term.write(`\r\n\x1b[31m${notice.text}\x1b[0m\r\n`);
    }
  };

  socket.onclose = () => {
    session.state = "offline";
    markTab(tabId(session.ip), "offline");
    session.term.write("\r\n\x1b[2m— сессия закрыта —\x1b[0m\r\n");
    // сервер снял конфигурацию при закрытии, история могла пополниться
    if (shownIp() === session.ip) {
      lockConfig(false);
      setTimeout(loadVersions, 1500);
    }
  };

  socket.onerror = () => {
    session.state = "offline";
    markTab(tabId(session.ip), "offline");
  };
}

function send(session, message) {
  if (session.socket && session.socket.readyState === WebSocket.OPEN) {
    session.socket.send(JSON.stringify(message));
  }
}

export function fitSession(session) {
  if (!session || session.pane.hidden) return;
  try {
    session.fit.fit();
  } catch (error) {
    /* размеры ещё не устоялись */
  }
}

export function fitActive() {
  for (const session of sessions.values()) fitSession(session);
}

function shutSession(session) {
  if (session.socket) {
    session.socket.onclose = null;
    session.socket.close();
  }
  session.term.dispose();
  sessions.delete(session.ip);
  cy.resize();
  layoutLabels();
}

export function closeTerminal(ip) {
  removeTab(tabId(ip));
}
