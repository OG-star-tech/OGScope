import { useI18n } from "../i18n/I18nProvider";

/** 嵌入相机调试页（逻辑在 debug.js）/ Embedded camera debug (logic in debug.js) */
export function CameraPage() {
  const { t } = useI18n();
  return (
    <div className="flex h-[calc(100vh-7rem)] min-h-[480px] flex-col gap-2">
      <p className="text-xs text-on-surface-variant">{t("console.camera.hint")}</p>
      <iframe
        title="camera-debug-embed"
        className="w-full flex-1 rounded-lg border border-outline-variant/30 bg-black"
        src="/debug/camera-embed"
      />
    </div>
  );
}
