// общее на всю страницу: список устройств, выбранное, корень схемы
export const state = {
  devices: [],
  selected: null,
  subnet: "",
  rootId: localStorage.getItem("root") || null,
};
