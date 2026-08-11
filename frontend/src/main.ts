import "@coreui/coreui/dist/css/coreui.min.css";

import { createPinia } from "pinia";
import { createApp } from "vue";
import CoreuiVue from "@coreui/vue";
import CIcon from "@coreui/icons-vue";

import App from "./App.vue";
import { iconsSet } from "./assets/coreui-icons";

createApp(App)
  .use(createPinia())
  .use(CoreuiVue)
  .provide("icons", iconsSet)
  .component("CIcon", CIcon)
  .mount("#app");
