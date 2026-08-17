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

export function setStatus(text) {
  document.getElementById("status").textContent = text;
}
