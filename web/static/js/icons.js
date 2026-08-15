// значки сетевых схем в изометрии: коммутатор это коробка, маршрутизатор
// цилиндр. цвет приходит снаружи и красит сам символ, рамки вокруг нет.
// свои, а не готовый набор, из-за лицензий. в коде, потому что продукт
// работает без интернета

function shape(build) {
  return (color) => {
    const svg =
      `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" ` +
      `viewBox="0 0 64 64" fill="none" stroke="${color}" stroke-width="2" ` +
      `stroke-linejoin="round" stroke-linecap="round">${build(color)}</svg>`;
    return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
  };
}

const face = (d, color, opacity) =>
  `<path d="${d}" fill="${color}" fill-opacity="${opacity}"/>`;

const ICONS = {
  // стрелки построены по направляющим верхней грани, она под 30 градусов.
  // по обычным осям они выглядят кривыми
  switch: shape(
    (c) =>
      face("M6 30 6 41 32 56 32 45Z", c, 0.34) +
      face("M58 30 58 41 32 56 32 45Z", c, 0.22) +
      face("M32 15 58 30 32 45 6 30Z", c, 0.14) +
      `<path d="M18.1 33 37.2 22" stroke-width="2.4"/>` +
      `<path d="M35.5 26 37.2 22 30.3 23"/>` +
      `<path d="M45.9 27 26.8 38" stroke-width="2.4"/>` +
      `<path d="M28.5 34 26.8 38 33.7 37"/>`
  ),

  router: shape(
    (c) =>
      face("M6 26v13a26 10 0 0 0 52 0V26Z", c, 0.3) +
      `<ellipse cx="32" cy="26" rx="26" ry="10" fill="${c}" fill-opacity="0.14"/>` +
      `<path d="M45 21.5H20" stroke-width="2.3"/>` +
      `<path d="M25 17 20.5 21.5 25 26"/>` +
      `<path d="M19 30.5h25" stroke-width="2.3"/>` +
      `<path d="M39 26 43.5 30.5 39 35"/>`
  ),

  multilayer: shape(
    (c) =>
      face("M8 26 8 40 32 54 32 40Z", c, 0.34) +
      face("M56 26 56 40 32 54 32 40Z", c, 0.22) +
      face("M32 12 56 26 32 40 8 26Z", c, 0.14) +
      `<path d="M32 19v13M32 32l-11-6.5M32 32l11-6.5M32 32v6"/>` +
      `<path d="M29.5 21 32 18.5 34.5 21"/>` +
      `<path d="M23.5 23 20.5 25.2 23.5 27.4"/>` +
      `<path d="M40.5 23 43.5 25.2 40.5 27.4"/>`
  ),

  firewall: shape(
    (c) =>
      face("M7 17h50v30H7Z", c, 0.2) +
      `<rect x="7" y="17" width="50" height="30" rx="2"/>` +
      `<path d="M7 27h50M7 37h50"/>` +
      `<path d="M23 17v10M41 17v10M15 27v10M32 27v10M49 27v10M23 37v10M41 37v10"/>`
  ),

  wifi: shape(
    (c) =>
      face("M12 38h40v14H12Z", c, 0.28) +
      `<rect x="12" y="38" width="40" height="14" rx="3"/>` +
      `<path d="M32 38V22"/>` +
      `<path d="M21 19a14 14 0 0 1 22 0"/>` +
      `<path d="M26 25a8 8 0 0 1 12 0"/>`
  ),

  unknown: shape(
    (c) =>
      face("M10 10h44v44H10Z", c, 0.12) +
      `<rect x="10" y="10" width="44" height="44" rx="7" stroke-dasharray="5 4"/>` +
      `<path d="M24 26a8 8 0 1 1 9 7.9V38" stroke-width="2.3"/>` +
      `<path d="M33 45v.3" stroke-width="2.6"/>`
  ),
};

export { ICONS };
