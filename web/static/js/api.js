export async function api(path, options) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (response.status === 401) location.href = "/";
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || "ошибка запроса");
  return body;
}

let statusTimer;

// сообщение всплывает в углу и само уходит. раньше оно оставалось в шапке
// навсегда, и через минуту уже нельзя было понять, к какому действию относится
export function setStatus(text) {
  const box = document.getElementById("status");
  document.getElementById("status-text").textContent = text;
  box.classList.toggle("shown", Boolean(text));
  clearTimeout(statusTimer);
  if (text) {
    statusTimer = setTimeout(() => box.classList.remove("shown"), 6000);
  }
}

document.getElementById("status-close").onclick = () => setStatus("");
