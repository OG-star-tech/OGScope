import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
// 打包进 bundle，避免 fetch /static 失败导致显示原始 key / Bundle JSON to avoid fetch failures
import enDict from "@i18n/analysis.en.json";
import zhDict from "@i18n/analysis.zh.json";

export type Locale = "zh" | "en";

type Ctx = {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
};

const I18nContext = createContext<Ctx | null>(null);

const BUNDLED: Record<Locale, Record<string, string>> = {
  zh: zhDict as Record<string, string>,
  en: enDict as Record<string, string>,
};

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>("zh");
  const [dict, setDict] = useState<Record<string, string>>(BUNDLED.zh);

  useEffect(() => {
    setDict(BUNDLED[locale]);
  }, [locale]);

  const t = useMemo(
    () => (key: string, vars?: Record<string, string | number>) => {
      let s = dict[key] ?? key;
      if (vars) {
        for (const [k, v] of Object.entries(vars)) {
          s = s.replace(new RegExp(`\\{${k}\\}`, "g"), String(v));
        }
      }
      return s;
    },
    [dict],
  );

  const value = useMemo<Ctx>(
    () => ({ locale, setLocale, t }),
    [locale, t],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): Ctx {
  const c = useContext(I18nContext);
  if (!c) throw new Error("useI18n must be used within I18nProvider");
  return c;
}
