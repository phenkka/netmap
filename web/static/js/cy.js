import { ICONS } from "./icons.js";
import { statusColor, themeColor } from "./colors.js";
import {
  ICON_SIZE,
  NODE_FONT,
  PORT_FONT,
  PORT_OFFSET,
  EDGE_FADE,
  OFFLINE_DIM,
} from "./const.js";

export const cy = cytoscape({
  container: document.getElementById("map"),
  minZoom: 0.3,
  maxZoom: 3,
  style: [
    {
      selector: "node",
      style: {
        "background-opacity": 0,
        "border-width": 0,
        "overlay-opacity": 0,
        "background-image": (n) =>
          (ICONS[n.data("type")] || ICONS.unknown)(statusColor(n.data("status"))),
        "background-fit": "contain",
        "background-width": "100%",
        "background-height": "100%",
        width: ICON_SIZE,
        height: ICON_SIZE,
        label: "data(label)",
        color: () => themeColor("--text"),
        "font-size": NODE_FONT,
        "text-wrap": "wrap",
        "text-justification": "center",
        "text-events": "no",
      },
    },
    {
      selector: "edge",
      style: {
        width: 2,
        "line-color": () => themeColor("--border"),
        "curve-style": "bezier",
        "source-text-offset": PORT_OFFSET,
        "target-text-offset": PORT_OFFSET,
        "font-size": PORT_FONT,
        color: () => themeColor("--muted"),
        "text-background-color": () => themeColor("--bg"),
        "text-background-opacity": 0.85,
        "text-background-padding": 3,
        "text-background-shape": "roundrectangle",
        "transition-property": "opacity",
        "transition-duration": EDGE_FADE,
        "transition-timing-function": "ease-out-sine",
      },
    },
    {
      selector: "edge.arriving",
      style: { opacity: 0 },
    },
    {
      selector: "edge.ports",
      style: {
        "line-color": () => themeColor("--accent"),
        color: () => themeColor("--text"),
        "z-index": 10,
      },
    },
  ],
});

// неавторизованные моргают: связей у них нет, пока не введён пароль.
// недоступные не моргают, они пароля не ждут, а просто погашены
let bright = true;
setInterval(() => {
  bright = !bright;
  cy.nodes().forEach((node) => {
    const status = node.data("status");
    if (status === "offline") {
      node.style("opacity", OFFLINE_DIM);
      return;
    }
    node.style("opacity", status !== "authorized" && !bright ? 0.35 : 1);
  });
}, 600);
