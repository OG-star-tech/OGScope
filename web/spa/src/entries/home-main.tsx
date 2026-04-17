import { createRoot } from "react-dom/client";

import { HomeApp } from "@core-ui/home/HomeApp";

/** 首页入口不使用 StrictMode，避免开发模式下重复挂载导致 legacy 脚本与 DOM 状态异常 / No StrictMode: avoids double legacy init in dev */
createRoot(document.getElementById("root")!).render(<HomeApp />);
