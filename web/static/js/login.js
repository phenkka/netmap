import { paintMock } from "./mock.js";

const form = document.getElementById("enter");
const problem = document.getElementById("problem");
const go = document.getElementById("go");
const login = document.getElementById("login");
const password = document.getElementById("password");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  problem.textContent = "";
  go.disabled = true;
  try {
    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ login: login.value, password: password.value }),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "не удалось войти");
    location.href = "/";
  } catch (error) {
    problem.textContent = error.message;
    go.disabled = false;
  }
});

const forgot = document.getElementById("forgot");
const cancel = document.getElementById("cancel");
const enter = document.getElementById("enter");
const restore = document.getElementById("restore");
const rGo = document.getElementById("r-go");
const rProblem = document.getElementById("r-problem");

function swap(recovering) {
  enter.hidden = recovering;
  restore.hidden = !recovering;
  (recovering ? document.getElementById("r-login") : login).focus();
}

forgot.addEventListener("click", () => swap(true));
cancel.addEventListener("click", () => swap(false));

restore.addEventListener("submit", async (event) => {
  event.preventDefault();
  rProblem.textContent = "";
  rGo.disabled = true;
  try {
    const response = await fetch("/api/recover", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        login: document.getElementById("r-login").value,
        recovery: document.getElementById("r-key").value,
        password: document.getElementById("r-password").value,
      }),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "не удалось восстановить доступ");
    location.href = "/";
  } catch (error) {
    rProblem.textContent = error.message;
    rGo.disabled = false;
  }
});

// без выданного ключа восстанавливать нечем, и предлагать это незачем
fetch("/api/recovery")
  .then((response) => response.json())
  .then((body) => {
    forgot.hidden = !body.offered;
  })
  .catch(() => {});

paintMock();
login.focus();
