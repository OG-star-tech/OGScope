# 星表数据库说明 / Star Catalog Database Notes

- 主库文件：`data/catalog/stars.db`
- 数据源（默认）：HYG Database v3（CSV）
- 用途：提供极轴解算与调试控制台的星点查询、匹配与维护

## 字段说明 / Fields

- `source_id`: 唯一标识 / Unique identifier
- `ra`, `dec`: 赤经赤纬（度）/ Right ascension and declination in degrees
- `pmra`, `pmdec`: 自行参数 / Proper motion parameters
- `phot_g_mean_mag`: 亮度星等 / Magnitude
- `name_en`, `name_zh`: 英文/中文名称
- `description_en`, `description_zh`: 英文/中文描述

## 维护方式 / Maintenance

- 可通过 `/api/catalog/*` 与 `/debug/analysis` 执行下载、索引、CRUD。
- 数据库文件会随 Git 提交与版本发行。
