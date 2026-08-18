export const ICON_SIZE = 140;
export const NODE_FONT = 14;
export const PORT_FONT = 12;
// отступ считается от края значка, а не от центра
export const PORT_OFFSET = 55;
// по углам значка пустота, считать её занятой нельзя
export const ICON_BODY = 0.72;
export const GAP = 10;

// недоступное устройство погашено, но остаётся читаемым
export const OFFLINE_DIM = 0.5;

export const HOVER_SCALE = 1.16;
export const PICKED_SCALE = 1.08;
export const TAP_SCALE = 1.26;

export const FOCUS_ZOOM = 0.625;
export const FOCUS_MOTION = 300;
// ждём второе нажатие, но меньше полного окна двойного, иначе отклик вялый
export const FOCUS_WAIT = 90;
// двойного клика у карты нет, считаем два нажатия подряд
export const DOUBLE_TAP = 350;

export const EDGE_FADE = 320;
export const MOTION = 420;
export const EASING = "ease-in-out";
// столько же стоит в style.css, в переменной --fade
export const THEME_FADE = 260;
export const REFRESH_EVERY = 3000;
export const PENDING_EVERY = 4000;

// столько же стоит в style.css, в переменной --sheet-fade
export const SHEET_FADE = 200;

export const VIEW_KEY = "netmap-view";
export const PLACES_KEY = "netmap-places";
