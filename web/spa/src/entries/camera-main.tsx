import React from "react";
import ReactDOM from "react-dom/client";
import { CameraConsoleApp } from "@dev-ui/camera/CameraConsoleApp";
import { SystemInfoProvider } from "@shared/context/SystemInfoContext";
import { I18nProvider } from "@shared/i18n/I18nProvider";
import "../index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <I18nProvider>
      <SystemInfoProvider>
        <CameraConsoleApp />
      </SystemInfoProvider>
    </I18nProvider>
  </React.StrictMode>,
);
