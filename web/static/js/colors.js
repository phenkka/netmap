export function themeColor(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function statusColor(status) {
  return themeColor(status === "authorized" ? "--pos" : "--neg");
}

// текст рисуется на холсте, css его не анимирует, переливаем цвет сами
export function mixColor(from, to, part) {
  const parse = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const a = parse(from);
  const b = parse(to);
  const channel = (i) => Math.round(a[i] + (b[i] - a[i]) * part);
  return (
    "#" +
    [0, 1, 2].map((i) => channel(i).toString(16).padStart(2, "0")).join("")
  );
}
