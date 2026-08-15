import { cy } from "./cy.js";
import { fadeTerminals } from "./terminal.js";
import { THEME_FADE } from "./const.js";

const themeButton = document.getElementById("theme");

export function applyTheme(light) {
  const root = document.documentElement;
  if (light) root.setAttribute("data-theme", "light");
  else root.removeAttribute("data-theme");

  themeButton.title = light ? "Включить тёмную тему" : "Включить светлую тему";
  try {
    localStorage.setItem("netmap-theme", light ? "light" : "dark");
  } catch (error) {
    /* режим инкогнито, тема просто не запомнится */
  }

  fadeTerminals(light);

  // холст перерисовываем несколько раз, чтобы не отставал от панелей
  const started = Date.now();
  const timer = setInterval(() => {
    cy.style().update();
    if (Date.now() - started > THEME_FADE) clearInterval(timer);
  }, 40);
}

themeButton.addEventListener("click", () =>
  applyTheme(document.documentElement.getAttribute("data-theme") !== "light")
);
