import { paintMock } from "./mock.js";

const card = document.getElementById("wizard");
const steps = [...document.querySelectorAll("#wizard .step")];
const dots = [...document.getElementById("dots").children];
const problem = document.getElementById("problem");
const found = document.getElementById("found");
const done = document.getElementById("done");

const login = document.getElementById("login");
const password = document.getElementById("password");
const again = document.getElementById("again");
const subnet = document.getElementById("subnet");

const READY = "Проверить и продолжить";
const STEP_MOTION = 300;

let least = 8;
let anyway = false;
let unlock = null;

function show(index) {
  problem.textContent = "";

  const was = card.offsetHeight;
  steps.forEach((step, i) => step.classList.toggle("on", i === index));
  dots.forEach((dot, i) => dot.classList.toggle("on", i === index));
  const now = card.offsetHeight;

  clearTimeout(unlock);
  card.style.height = `${was}px`;
  requestAnimationFrame(() => {
    card.style.height = `${now}px`;
  });
  unlock = setTimeout(() => {
    card.style.height = "";
  }, STEP_MOTION + 40);

  const field = steps[index].querySelector("input");
  if (field) field.focus();
}

function stop(message) {
  problem.textContent = message;
  return false;
}

async function post(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || "ошибка запроса");
  return body;
}

function credentialsReady() {
  if (!login.value.trim()) return stop("логин не заполнен");
  if (password.value.length < least) return stop(`пароль короче ${least} знаков`);
  if (password.value !== again.value) return stop("пароли не совпадают");
  return true;
}

async function ask() {
  const body = await (await fetch("/api/setup")).json();
  least = body.least;
  password.placeholder = `Пароль, не короче ${least} знаков`;

  if (!body.networks.length) return;
  if (body.networks.length === 1) subnet.value = body.networks[0];

  document.getElementById("whence").hidden = false;
  found.innerHTML = body.networks
    .map((net) => `<button type="button" class="hint-net">${net}</button>`)
    .join("");
  found.querySelectorAll(".hint-net").forEach((chip) => {
    chip.addEventListener("click", () => {
      subnet.value = chip.textContent;
      reset();
    });
  });
}

function reset() {
  anyway = false;
  done.textContent = READY;
  problem.textContent = "";
}

function busy(text) {
  done.textContent = text;
  done.classList.add("waiting");
}

function calm() {
  done.classList.remove("waiting");
}

// пустая сеть обходится за hosts / 512 * полсекунды, дольше двадцати секунд
// это только /17 и крупнее
function large(cidr) {
  const bits = Number(cidr.split("/")[1]);
  return Number.isInteger(bits) && bits < 18;
}

async function finish() {
  if (!subnet.value.trim()) return stop("подсеть не заполнена");

  done.disabled = true;
  try {
    if (!anyway) {
      busy(large(subnet.value) ? "Проверяю сеть, это надолго" : "Проверяю сеть");
      const check = await post("/api/setup/check", { subnet: subnet.value });
      calm();

      const trouble = !check.attached
        ? `машина не подключена к этой сети, MAC-адреса будут недоступны. Свои сети: ${check.networks.join(", ")}`
        : !check.checked
          ? `в сети ${check.hosts} адресов, обходить её для проверки слишком долго`
          : !check.found
            ? "обошли сеть целиком, по SSH не ответил никто"
            : "";

      if (trouble) {
        anyway = true;
        done.textContent = "Всё равно продолжить";
        done.disabled = false;
        return stop(trouble);
      }
      problem.textContent = "";
    }

    busy("Настраиваю");
    await post("/api/setup", {
      login: login.value,
      password: password.value,
      subnet: subnet.value,
    });
    location.href = "/";
  } catch (error) {
    calm();
    stop(error.message);
    done.textContent = anyway ? "Всё равно продолжить" : READY;
    done.disabled = false;
  }
}

steps[0].querySelector(".next").addEventListener("click", () => show(1));
steps[1].querySelector(".back").addEventListener("click", () => show(0));
steps[2].querySelector(".back").addEventListener("click", () => show(1));

steps[1].addEventListener("submit", (event) => {
  event.preventDefault();
  if (credentialsReady()) show(2);
});

steps[2].addEventListener("submit", (event) => {
  event.preventDefault();
  finish();
});

subnet.addEventListener("input", reset);

paintMock();
ask();
