import { useI18n } from "@shared/i18n/I18nProvider";

const pageMeta = {
  sensors: {
    titleKey: "sys.placeholder.sensors.title",
    descKey: "sys.placeholder.sensors.desc",
    blocks: [
      "sys.placeholder.sensors.block1",
      "sys.placeholder.sensors.block2",
      "sys.placeholder.sensors.block3",
    ],
  },
  hmi: {
    titleKey: "sys.placeholder.hmi.title",
    descKey: "sys.placeholder.hmi.desc",
    blocks: [
      "sys.placeholder.hmi.block1",
      "sys.placeholder.hmi.block2",
      "sys.placeholder.hmi.block3",
    ],
  },
  power: {
    titleKey: "sys.placeholder.power.title",
    descKey: "sys.placeholder.power.desc",
    blocks: [
      "sys.placeholder.power.block1",
      "sys.placeholder.power.block2",
      "sys.placeholder.power.block3",
    ],
  },
} as const;

export function PlaceholderPage({ scope }: { scope: "sensors" | "power" | "hmi" }) {
  const { t } = useI18n();
  const meta = pageMeta[scope];
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header>
        <div className="text-[10px] uppercase tracking-[0.14em] text-on-surface-variant">
          {t("sys.placeholder.breadcrumb")}
        </div>
        <h2 className="mt-1 font-headline text-3xl font-black tracking-tight">{t(meta.titleKey)}</h2>
        <p className="text-sm text-on-surface-variant">{t(meta.descKey)}</p>
      </header>

      <section className="grid grid-cols-12 gap-4">
        {meta.blocks.map((nameKey) => (
          <article
            key={nameKey}
            className="col-span-12 rounded-xl border border-dashed border-outline-variant/40 bg-surface-container/60 p-5 md:col-span-4"
          >
            <p className="text-[10px] uppercase tracking-widest text-primary">{t("sys.placeholder.block")}</p>
            <h3 className="mt-2 text-lg font-semibold">{t(nameKey)}</h3>
            <p className="mt-2 text-sm text-on-surface-variant">{t("sys.placeholder.desc")}</p>
          </article>
        ))}
      </section>

      <section className="rounded-xl border border-outline-variant/20 bg-surface-container-low p-4">
        <p className="font-mono text-xs text-on-surface-variant">{t("sys.placeholder.status")}</p>
      </section>
    </div>
  );
}
