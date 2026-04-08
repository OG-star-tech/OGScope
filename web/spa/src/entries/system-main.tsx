import React from "react";
import ReactDOM from "react-dom/client";
import { SystemConsoleApp } from "@apps/system/SystemConsoleApp";
import { SystemInfoProvider } from "@shared/context/SystemInfoContext";
import { I18nProvider } from "@shared/i18n/I18nProvider";
import "../index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <I18nProvider>
      <SystemInfoProvider>
        <SystemConsoleApp />
      </SystemInfoProvider>
    </I18nProvider>
  </React.StrictMode>,
);
