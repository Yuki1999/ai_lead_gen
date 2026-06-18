import { createApp } from "vue";
import App from "./App.vue";
import { router } from "./router";

// Inter — the brand font listed in `--font-family` and the Naive
// `theme.common.fontFamily`. Loading actual font files (rather than
// relying on the system fallback) ensures consistent metrics across
// macOS / Windows / Linux. Latin subset only (≈30 KB per weight).
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";

import "./styles.css";

createApp(App).use(router).mount("#app");
