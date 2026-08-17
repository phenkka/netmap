import { ICONS } from "./icons.js";
import { themeColor } from "./colors.js";

const SHAPE = [
  { x: 50, y: 22, type: "switch", live: true },
  { x: 24, y: 55, type: "switch", live: true },
  { x: 76, y: 55, type: "switch", live: false },
  { x: 38, y: 84, type: "router", live: false },
  { x: 78, y: 82, type: "firewall", live: true },
];

const WIRES = [[0, 1], [0, 2], [1, 2], [1, 3], [2, 4]];

export function paintMock() {
  const wires = WIRES.map(
    ([a, b]) =>
      `<line x1="${SHAPE[a].x}%" y1="${SHAPE[a].y}%" x2="${SHAPE[b].x}%" y2="${SHAPE[b].y}%"/>`
  ).join("");

  const nodes = SHAPE.map((node) => {
    const icon = ICONS[node.type](themeColor(node.live ? "--pos" : "--neg"));
    return `<img src="${icon}" style="left:${node.x}%;top:${node.y}%">`;
  }).join("");

  document.getElementById("map").innerHTML = `<svg>${wires}</svg>${nodes}`;
}
