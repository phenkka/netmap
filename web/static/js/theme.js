// тема: системная, тёмная или светлая. выбор хранится, а не вычисляется каждый раз

import { cy } from "./cy.js";
import { fadeTerminals } from "./terminal.js";
import { THEME_FADE } from "./const.js";

const KEY = "netmap-theme";
const CHOICES = ["system", "dark", "light"];
const system = window.matchMedia("(prefers-color-scheme: light)");

export function themeChoice() {
  let saved = null;
  try {
    saved = localStorage.getItem(KEY);
  } catch (error) {
    /* инкогнито, остаёмся на системной */
  }
  return CHOICES.includes(saved) ? saved : "system";
}

export function themeIsLight(choice = themeChoice()) {
  return choice === "light" || (choice === "system" && system.matches);
}

export function applyTheme(choice) {
  try {
    localStorage.setItem(KEY, choice);
  } catch (error) {
    /* режим инкогнито, тема просто не запомнится */
  }
  paint(themeIsLight(choice));
}

function paint(light) {
  const root = document.documentElement;
  if (light) root.setAttribute("data-theme", "light");
  else root.removeAttribute("data-theme");

  fadeTerminals(light);

  // холст цвета из css сам не подхватывает, поэтому перерисовываем его
  // весь переход, кадр за кадром
  const started = performance.now();
  const step = (now) => {
    cy.style().update();
    if (now - started < THEME_FADE) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

// пока выбрана системная тема, идём за системой
system.addEventListener("change", () => {
  if (themeChoice() === "system") paint(system.matches);
});
