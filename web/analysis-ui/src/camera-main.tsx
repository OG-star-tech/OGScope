import React from "react";
import ReactDOM from "react-dom/client";
import { I18nProvider } from "./i18n/I18nProvider";
import { SystemInfoProvider } from "./context/SystemInfoContext";
import { CameraConsoleApp } from "./camera/CameraConsoleApp";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <I18nProvider>
      <SystemInfoProvider>
        <CameraConsoleApp />
      </SystemInfoProvider>
    </I18nProvider>
  </React.StrictMode>,
);
