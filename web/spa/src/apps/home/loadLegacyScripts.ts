/** 按顺序加载首页既有 /static/js 脚本链（与旧 Jinja 页一致）/ Legacy script chain for HUD */

export const HOME_LEGACY_SCRIPTS: string[] = [
  "/static/js/shared/utils.js",
  "/static/js/shared/constants.js",
  "/static/js/shared/api.js",
  "/static/js/core/ui.js",
  "/static/js/core/camera.js",
  "/static/js/core/alignment.js",
  "/static/js/app-home-analysis.js",
];

export function loadScriptChain(urls: string[]): Promise<void> {
  return urls.reduce(
    (chain, url) =>
      chain.then(
        () =>
          new Promise<void>((resolve, reject) => {
            const existing = document.querySelector(`script[src="${url}"]`);
            if (existing) {
              resolve();
              return;
            }
            const s = document.createElement("script");
            s.src = url;
            s.async = false;
            s.onload = () => resolve();
            s.onerror = () => reject(new Error(`Failed to load ${url}`));
            document.body.appendChild(s);
          }),
      ),
    Promise.resolve(),
  );
}
