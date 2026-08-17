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

paintMock();
login.focus();
