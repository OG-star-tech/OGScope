"""
星表数据服务 / Catalog data service
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from math import cos, radians
from pathlib import Path
from typing import Any
from urllib.request import urlretrieve

from ogscope.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CatalogRecord:
    """星表记录 / Catalog record"""

    source_id: str
    ra: float
    dec: float
    pmra: float
    pmdec: float
    phot_g_mean_mag: float
    name_en: str
    name_zh: str
    description_en: str
    description_zh: str

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "CatalogRecord":
        return cls(
            source_id=row["source_id"],
            ra=float(row["ra"]),
            dec=float(row["dec"]),
            pmra=float(row.get("pmra", 0.0)),
            pmdec=float(row.get("pmdec", 0.0)),
            phot_g_mean_mag=float(row["phot_g_mean_mag"]),
            name_en=row.get("name_en", row["source_id"]),
            name_zh=row.get("name_zh", row.get("name_en", row["source_id"])),
            description_en=row.get("description_en", ""),
            description_zh=row.get("description_zh", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "ra": self.ra,
            "dec": self.dec,
            "pmra": self.pmra,
            "pmdec": self.pmdec,
            "phot_g_mean_mag": self.phot_g_mean_mag,
            "name_en": self.name_en,
            "name_zh": self.name_zh,
            "description_en": self.description_en,
            "description_zh": self.description_zh,
        }


class CatalogService:
    """星表服务（SQLite 主存储） / Catalog service with SQLite primary storage"""

    RAW_FILE_NAME = "catalog_raw.csv"
    MANIFEST_NAME = "manifest.json"
    RAW_DIR_NAME = "raw"
    META_DIR_NAME = "meta"
    DB_FILE_NAME = "stars.db"
    HYG_URL = (
        "https://raw.githubusercontent.com/astronexus/HYG-Database/main/"
        "hyg/CURRENT/hygdata_v41.csv"
    )

    _COMMON_CN_NAMES: dict[str, str] = {
        "sirius": "天狼星",
        "canopus": "老人星",
        "arcturus": "大角星",
        "vega": "织女星",
        "capella": "五车二",
        "rigel": "参宿七",
        "procyon": "南河三",
        "betelgeuse": "参宿四",
        "achernar": "水委一",
        "hadar": "马腹一",
        "altair": "牛郎星",
        "aldebaran": "毕宿五",
        "spica": "角宿一",
        "antares": "心宿二",
        "pollux": "北河三",
        "fomalhaut": "北落师门",
        "deneb": "天津四",
        "regulus": "轩辕十四",
        "castor": "北河二",
        "bellatrix": "参宿五",
        "mirfak": "天船三",
        "alnilam": "参宿二",
        "alnair": "鹤一",
        "alioth": "玉衡",
        "dubhe": "天枢",
        "merak": "天璇",
        "polaris": "北极星",
    }

    _SEED_ROWS: tuple[dict[str, str], ...] = (
        {"source_id": "hip11767", "ra": "37.95456067", "dec": "89.26410897", "pmra": "44.22", "pmdec": "-11.74", "phot_g_mean_mag": "1.97"},
        {"source_id": "hip32349", "ra": "101.28715533", "dec": "-16.71611586", "pmra": "-546.01", "pmdec": "-1223.07", "phot_g_mean_mag": "-1.46"},
        {"source_id": "hip30438", "ra": "95.98787778", "dec": "-52.69571722", "pmra": "19.93", "pmdec": "23.24", "phot_g_mean_mag": "-0.72"},
        {"source_id": "hip69673", "ra": "213.91530029", "dec": "19.18240917", "pmra": "-1093.39", "pmdec": "-1999.85", "phot_g_mean_mag": "0.03"},
        {"source_id": "hip71683", "ra": "219.89972883", "dec": "-60.83514707", "pmra": "-3606.35", "pmdec": "686.92", "phot_g_mean_mag": "-0.27"},
        {"source_id": "hip91262", "ra": "279.23473479", "dec": "38.78368896", "pmra": "200.94", "pmdec": "286.23", "phot_g_mean_mag": "0.03"},
        {"source_id": "hip113368", "ra": "344.41269272", "dec": "-29.62223628", "pmra": "329.95", "pmdec": "-164.67", "phot_g_mean_mag": "1.16"},
        {"source_id": "hip21421", "ra": "68.98016279", "dec": "16.50930235", "pmra": "24.95", "pmdec": "-14.53", "phot_g_mean_mag": "0.85"},
        {"source_id": "hip65474", "ra": "201.29824762", "dec": "-11.16132218", "pmra": "-109.23", "pmdec": "-73.36", "phot_g_mean_mag": "0.98"},
        {"source_id": "hip80763", "ra": "247.35191583", "dec": "-26.43200231", "pmra": "-8.53", "pmdec": "-23.85", "phot_g_mean_mag": "1.06"},
    )

    def __init__(self) -> None:
        settings = get_settings()
        self.catalog_dir = settings.catalog_dir
        self.raw_dir = self.catalog_dir / self.RAW_DIR_NAME
        self.meta_dir = self.catalog_dir / self.META_DIR_NAME
        self.db_path = self.catalog_dir / self.DB_FILE_NAME
        self._ensure_dirs()
        self._init_db()

    @property
    def raw_file(self) -> Path:
        return self.raw_dir / self.RAW_FILE_NAME

    @property
    def manifest_file(self) -> Path:
        return self.meta_dir / self.MANIFEST_NAME

    def reconfigure_storage(self, catalog_dir: Path) -> None:
        """重新配置存储路径 / Reconfigure storage paths"""
        self.catalog_dir = catalog_dir
        self.raw_dir = self.catalog_dir / self.RAW_DIR_NAME
        self.meta_dir = self.catalog_dir / self.META_DIR_NAME
        self.db_path = self.catalog_dir / self.DB_FILE_NAME
        self._ensure_dirs()
        self._init_db()

    def download_catalog(
        self, source: str = "seed", url: str | None = None, magnitude_limit: float = 8.5
    ) -> dict[str, Any]:
        """下载或生成星表，并导入数据库 / Download or generate catalog and import to DB"""
        if source == "seed":
            self._write_seed_catalog(self.raw_file, magnitude_limit=magnitude_limit)
        elif source == "hyg":
            target_url = url or self.HYG_URL
            if target_url.endswith(".gz"):
                gz_path = self.raw_dir / "hyg_catalog.csv.gz"
                self._download_file(target_url, gz_path)
                self._gunzip_file(gz_path, self.raw_file)
            else:
                self._download_file(target_url, self.raw_file)
        elif source == "url":
            if not url:
                raise ValueError("url source 模式必须提供 URL / URL is required for url source")
            self._download_file(url, self.raw_file)
        else:
            raise ValueError("不支持的 source，允许 seed / hyg / url / Unsupported source")

        imported_count = self._import_csv_to_db(self.raw_file, magnitude_limit, source)
        self._set_meta("source", source)
        self._set_meta("magnitude_limit", str(magnitude_limit))
        self._set_meta("source_sha256", self._sha256_of_file(self.raw_file))
        self._set_meta("status", "imported")
        self._set_meta("last_download_at", datetime.now(timezone.utc).isoformat())
        return {
            "success": True,
            "source": source,
            "path": str(self.raw_file),
            "imported_count": imported_count,
            "message": "星表已导入数据库 / Catalog imported into SQLite",
        }

    def build_index(
        self, magnitude_limit: float = 8.5, ra_bin_size_deg: float = 15.0
    ) -> dict[str, Any]:
        """构建数据库索引与统计 / Build DB indexes and stats"""
        with self._connect() as conn:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_stars_ra_now ON stars(ra_now)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_stars_dec_now ON stars(dec_now)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_stars_mag ON stars(phot_g_mean_mag)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_stars_source_id ON stars(source_id)"
            )
            conn.execute("ANALYZE")

            count_row = conn.execute(
                "SELECT COUNT(*) AS c FROM stars WHERE phot_g_mean_mag <= ?",
                (magnitude_limit,),
            ).fetchone()
            record_count = int(count_row["c"]) if count_row else 0
            bucket_rows = conn.execute(
                "SELECT CAST(ra_now / ? AS INTEGER) AS rb, COUNT(*) AS c "
                "FROM stars WHERE phot_g_mean_mag <= ? GROUP BY rb",
                (ra_bin_size_deg, magnitude_limit),
            ).fetchall()
            bucket_count = len(bucket_rows)

        now_iso = datetime.now(timezone.utc).isoformat()
        manifest = {
            "generated_at": now_iso,
            "source_file": str(self.raw_file),
            "db_path": str(self.db_path),
            "magnitude_limit": magnitude_limit,
            "ra_bin_size_deg": ra_bin_size_deg,
            "record_count": record_count,
            "bucket_count": bucket_count,
            "source_sha256": self._meta("source_sha256", ""),
            "epoch": "JNow(approx)",
            "status": "ready",
        }
        self.manifest_file.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._set_meta("status", "ready")
        self._set_meta("ra_bin_size_deg", str(ra_bin_size_deg))
        self._set_meta("magnitude_limit", str(magnitude_limit))
        self._set_meta("last_build_at", now_iso)
        return {"success": True, **manifest}

    def get_status(self) -> dict[str, Any]:
        """获取星表状态 / Get catalog status"""
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM stars").fetchone()
            total_count = int(row["c"]) if row else 0
        ready = total_count > 0 and self._meta("status", "") in {"ready", "imported"}
        return {
            "ready": ready,
            "status": self._meta("status", "empty"),
            "catalog_dir": str(self.catalog_dir),
            "db_path": str(self.db_path),
            "source": self._meta("source", ""),
            "magnitude_limit": float(self._meta("magnitude_limit", "8.5")),
            "ra_bin_size_deg": float(self._meta("ra_bin_size_deg", "15.0")),
            "last_download_at": self._meta("last_download_at", ""),
            "last_build_at": self._meta("last_build_at", ""),
            "record_count": total_count,
        }

    def load_records_for_region(
        self, ra_deg: float, search_bins: int = 1
    ) -> list[CatalogRecord]:
        """按 RA 区域读取星点 / Load stars by RA region"""
        if not self.get_status().get("ready"):
            return []
        bin_size = float(self._meta("ra_bin_size_deg", "15.0"))
        half_width = max(1.0, (search_bins + 1) * bin_size)
        ra_center = ra_deg % 360.0
        ra_min = ra_center - half_width
        ra_max = ra_center + half_width

        query = (
            "SELECT source_id, ra, dec, pmra, pmdec, phot_g_mean_mag, "
            "name_en, name_zh, description_en, description_zh FROM stars "
            "WHERE phot_g_mean_mag <= ? AND "
        )
        mag_limit = float(self._meta("magnitude_limit", "8.5"))
        params: tuple[float, ...]
        if ra_min < 0:
            query += "(ra_now >= ? OR ra_now <= ?) "
            params = (mag_limit, 360.0 + ra_min, ra_max)
        elif ra_max >= 360.0:
            query += "(ra_now >= ? OR ra_now <= ?) "
            params = (mag_limit, ra_min, ra_max - 360.0)
        else:
            query += "ra_now BETWEEN ? AND ? "
            params = (mag_limit, ra_min, ra_max)
        query += "ORDER BY phot_g_mean_mag ASC LIMIT 500"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            CatalogRecord(
                source_id=str(row["source_id"]),
                ra=float(row["ra"]),
                dec=float(row["dec"]),
                pmra=float(row["pmra"]),
                pmdec=float(row["pmdec"]),
                phot_g_mean_mag=float(row["phot_g_mean_mag"]),
                name_en=str(row["name_en"]),
                name_zh=str(row["name_zh"]),
                description_en=str(row["description_en"]),
                description_zh=str(row["description_zh"]),
            )
            for row in rows
        ]

    def list_stars(
        self,
        limit: int = 100,
        offset: int = 0,
        source_query: str | None = None,
        min_mag: float | None = None,
        max_mag: float | None = None,
    ) -> dict[str, Any]:
        """分页查询星点 / List stars with pagination"""
        where: list[str] = []
        params: list[Any] = []
        if source_query:
            where.append("source_id LIKE ?")
            params.append(f"%{source_query}%")
        if min_mag is not None:
            where.append("phot_g_mean_mag >= ?")
            params.append(min_mag)
        if max_mag is not None:
            where.append("phot_g_mean_mag <= ?")
            params.append(max_mag)
        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        sql = (
            "SELECT source_id, ra, dec, pmra, pmdec, phot_g_mean_mag, "
            "name_en, name_zh, description_en, description_zh, "
            "ra_now, dec_now, updated_at "
            f"FROM stars {where_clause} ORDER BY phot_g_mean_mag ASC LIMIT ? OFFSET ?"
        )
        count_sql = f"SELECT COUNT(*) AS c FROM stars {where_clause}"
        params_with_page = [*params, max(1, limit), max(0, offset)]
        with self._connect() as conn:
            rows = conn.execute(sql, params_with_page).fetchall()
            count_row = conn.execute(count_sql, params).fetchone()
        return {
            "total": int(count_row["c"]) if count_row else 0,
            "items": [dict(row) for row in rows],
        }

    def get_star(self, source_id: str) -> dict[str, Any] | None:
        """按 source_id 查询星点 / Get star by source_id"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT source_id, ra, dec, pmra, pmdec, phot_g_mean_mag, "
                "name_en, name_zh, description_en, description_zh, "
                "ra_now, dec_now, updated_at "
                "FROM stars WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        return dict(row) if row else None

    def create_star(self, payload: dict[str, Any]) -> dict[str, Any]:
        """新增星点 / Create star"""
        record = CatalogRecord(
            source_id=str(payload["source_id"]),
            ra=float(payload["ra"]),
            dec=float(payload["dec"]),
            pmra=float(payload.get("pmra", 0.0)),
            pmdec=float(payload.get("pmdec", 0.0)),
            phot_g_mean_mag=float(payload["phot_g_mean_mag"]),
            name_en=str(payload.get("name_en", payload["source_id"])),
            name_zh=str(payload.get("name_zh", payload.get("name_en", payload["source_id"]))),
            description_en=str(payload.get("description_en", "")),
            description_zh=str(payload.get("description_zh", "")),
        )
        normalized = self._normalize_record_to_observation_epoch(record)
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO stars (source_id, ra, dec, pmra, pmdec, phot_g_mean_mag, "
                "name_en, name_zh, description_en, description_zh, "
                "ra_now, dec_now, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    normalized.source_id,
                    normalized.ra,
                    normalized.dec,
                    normalized.pmra,
                    normalized.pmdec,
                    normalized.phot_g_mean_mag,
                    normalized.name_en,
                    normalized.name_zh,
                    normalized.description_en,
                    normalized.description_zh,
                    normalized.ra,
                    normalized.dec,
                    now_iso,
                    now_iso,
                ),
            )
        result = self.get_star(normalized.source_id)
        if not result:
            raise ValueError("新增星点失败 / Failed to create star")
        return result

    def update_star(self, source_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """更新星点 / Update star"""
        existing = self.get_star(source_id)
        if not existing:
            raise FileNotFoundError("星点不存在 / Star not found")
        merged = {
            "source_id": source_id,
            "ra": payload.get("ra", existing["ra"]),
            "dec": payload.get("dec", existing["dec"]),
            "pmra": payload.get("pmra", existing["pmra"]),
            "pmdec": payload.get("pmdec", existing["pmdec"]),
            "phot_g_mean_mag": payload.get(
                "phot_g_mean_mag", existing["phot_g_mean_mag"]
            ),
            "name_en": payload.get("name_en", existing["name_en"]),
            "name_zh": payload.get("name_zh", existing["name_zh"]),
            "description_en": payload.get("description_en", existing["description_en"]),
            "description_zh": payload.get("description_zh", existing["description_zh"]),
        }
        normalized = self._normalize_record_to_observation_epoch(
            CatalogRecord(
                source_id=str(merged["source_id"]),
                ra=float(merged["ra"]),
                dec=float(merged["dec"]),
                pmra=float(merged["pmra"]),
                pmdec=float(merged["pmdec"]),
                phot_g_mean_mag=float(merged["phot_g_mean_mag"]),
                name_en=str(merged["name_en"]),
                name_zh=str(merged["name_zh"]),
                description_en=str(merged["description_en"]),
                description_zh=str(merged["description_zh"]),
            )
        )
        with self._connect() as conn:
            conn.execute(
                "UPDATE stars SET ra = ?, dec = ?, pmra = ?, pmdec = ?, phot_g_mean_mag = ?, "
                "name_en = ?, name_zh = ?, description_en = ?, description_zh = ?, "
                "ra_now = ?, dec_now = ?, updated_at = ? WHERE source_id = ?",
                (
                    normalized.ra,
                    normalized.dec,
                    normalized.pmra,
                    normalized.pmdec,
                    normalized.phot_g_mean_mag,
                    normalized.name_en,
                    normalized.name_zh,
                    normalized.description_en,
                    normalized.description_zh,
                    normalized.ra,
                    normalized.dec,
                    datetime.now(timezone.utc).isoformat(),
                    source_id,
                ),
            )
        result = self.get_star(source_id)
        if not result:
            raise ValueError("更新星点失败 / Failed to update star")
        return result

    def delete_star(self, source_id: str) -> bool:
        """删除星点 / Delete star"""
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM stars WHERE source_id = ?", (source_id,))
            return cursor.rowcount > 0

    def _ensure_dirs(self) -> None:
        self.catalog_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.meta_dir.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        try:
            self._create_or_migrate_db()
            return
        except sqlite3.DatabaseError as exc:
            if not self._is_malformed_error(exc):
                raise
            logger.error(
                "检测到星表数据库损坏，准备自动恢复 / Corrupted catalog DB detected, starting auto-recovery: %s",
                exc,
            )

        self._recover_malformed_db()
        self._create_or_migrate_db()
        self._set_meta(
            "recovered_from_corruption_at",
            datetime.now(timezone.utc).isoformat(),
        )

    def _create_or_migrate_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS stars ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "source_id TEXT NOT NULL UNIQUE, "
                "ra REAL NOT NULL, "
                "dec REAL NOT NULL, "
                "pmra REAL NOT NULL DEFAULT 0, "
                "pmdec REAL NOT NULL DEFAULT 0, "
                "phot_g_mean_mag REAL NOT NULL, "
                "name_en TEXT NOT NULL DEFAULT '', "
                "name_zh TEXT NOT NULL DEFAULT '', "
                "description_en TEXT NOT NULL DEFAULT '', "
                "description_zh TEXT NOT NULL DEFAULT '', "
                "ra_now REAL NOT NULL, "
                "dec_now REAL NOT NULL, "
                "created_at TEXT NOT NULL, "
                "updated_at TEXT NOT NULL"
                ")"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS catalog_meta ("
                "key TEXT PRIMARY KEY, "
                "value TEXT NOT NULL"
                ")"
            )
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        self._migrate_schema()

    @staticmethod
    def _is_malformed_error(exc: sqlite3.DatabaseError) -> bool:
        message = str(exc).lower()
        return (
            "malformed" in message
            or "disk image is malformed" in message
            or "file is not a database" in message
        )

    def _recover_malformed_db(self) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = self.catalog_dir / f"stars_corrupt_{timestamp}.db"
        db_exists = self.db_path.exists()
        if db_exists:
            try:
                self.db_path.replace(backup_path)
            except Exception:
                try:
                    self.db_path.unlink()
                except FileNotFoundError:
                    pass
        for sidecar in (
            self.db_path.with_suffix(".db-wal"),
            self.db_path.with_suffix(".db-shm"),
        ):
            try:
                sidecar.unlink()
            except FileNotFoundError:
                pass
        logger.warning(
            "星表数据库已恢复，原损坏文件备份到: %s / Catalog DB recovered, backup saved at: %s",
            str(backup_path) if db_exists else "N/A",
            str(backup_path) if db_exists else "N/A",
        )

    def _migrate_schema(self) -> None:
        """为旧库补齐新字段 / Add missing columns for legacy DB"""
        required_columns = {
            "name_en": "TEXT NOT NULL DEFAULT ''",
            "name_zh": "TEXT NOT NULL DEFAULT ''",
            "description_en": "TEXT NOT NULL DEFAULT ''",
            "description_zh": "TEXT NOT NULL DEFAULT ''",
        }
        with self._connect() as conn:
            rows = conn.execute("PRAGMA table_info(stars)").fetchall()
            existing = {str(row["name"]) for row in rows}
            for column_name, column_spec in required_columns.items():
                if column_name in existing:
                    continue
                conn.execute(
                    f"ALTER TABLE stars ADD COLUMN {column_name} {column_spec}"
                )

    def _set_meta(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO catalog_meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def _meta(self, key: str, default: str) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM catalog_meta WHERE key = ?", (key,)
            ).fetchone()
        return str(row["value"]) if row else default

    def _write_seed_catalog(self, target: Path, magnitude_limit: float) -> None:
        rows = []
        for row in self._SEED_ROWS:
            if float(row["phot_g_mean_mag"]) > magnitude_limit:
                continue
            enriched = dict(row)
            enriched["name_en"] = row["source_id"]
            enriched["name_zh"] = row["source_id"]
            enriched["description_en"] = "Seed catalog star / 种子星表星点"
            enriched["description_zh"] = "种子星表星点 / Seed catalog star"
            rows.append(enriched)
        with target.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "source_id",
                    "ra",
                    "dec",
                    "pmra",
                    "pmdec",
                    "phot_g_mean_mag",
                    "name_en",
                    "name_zh",
                    "description_en",
                    "description_zh",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

    def _import_csv_to_db(
        self, csv_file: Path, magnitude_limit: float, source: str
    ) -> int:
        dedup_source_ids: set[str] = set()
        now_iso = datetime.now(timezone.utc).isoformat()
        imported_count = 0
        with csv_file.open("r", encoding="utf-8") as f, self._connect() as conn:
            reader = csv.DictReader(f)
            for raw in reader:
                try:
                    record = self._record_from_raw_row(raw, source)
                except (KeyError, ValueError):
                    continue
                if record.source_id in dedup_source_ids:
                    continue
                if not (-90.0 <= record.dec <= 90.0 and 0.0 <= record.ra <= 360.0):
                    continue
                if record.phot_g_mean_mag > magnitude_limit:
                    continue
                normalized = self._normalize_record_to_observation_epoch(record)
                conn.execute(
                    "INSERT INTO stars (source_id, ra, dec, pmra, pmdec, phot_g_mean_mag, "
                    "name_en, name_zh, description_en, description_zh, "
                    "ra_now, dec_now, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(source_id) DO UPDATE SET "
                    "ra = excluded.ra, dec = excluded.dec, pmra = excluded.pmra, pmdec = excluded.pmdec, "
                    "phot_g_mean_mag = excluded.phot_g_mean_mag, "
                    "name_en = excluded.name_en, name_zh = excluded.name_zh, "
                    "description_en = excluded.description_en, description_zh = excluded.description_zh, "
                    "ra_now = excluded.ra_now, dec_now = excluded.dec_now, updated_at = excluded.updated_at",
                    (
                        normalized.source_id,
                        normalized.ra,
                        normalized.dec,
                        normalized.pmra,
                        normalized.pmdec,
                        normalized.phot_g_mean_mag,
                        normalized.name_en,
                        normalized.name_zh,
                        normalized.description_en,
                        normalized.description_zh,
                        normalized.ra,
                        normalized.dec,
                        now_iso,
                        now_iso,
                    ),
                )
                dedup_source_ids.add(record.source_id)
                imported_count += 1
        return imported_count

    def _normalize_record_to_observation_epoch(self, record: CatalogRecord) -> CatalogRecord:
        now_year = datetime.now(timezone.utc).year
        years = max(0.0, float(now_year - 2016))
        dec_offset_deg = (record.pmdec * years) / 3_600_000.0
        corrected_dec = max(-90.0, min(90.0, record.dec + dec_offset_deg))
        cos_dec = max(0.01, cos(radians(corrected_dec)))
        ra_offset_deg = (record.pmra * years) / 3_600_000.0 / cos_dec
        corrected_ra = (record.ra + ra_offset_deg) % 360.0
        return CatalogRecord(
            source_id=record.source_id,
            ra=corrected_ra,
            dec=corrected_dec,
            pmra=record.pmra,
            pmdec=record.pmdec,
            phot_g_mean_mag=record.phot_g_mean_mag,
            name_en=record.name_en,
            name_zh=record.name_zh,
            description_en=record.description_en,
            description_zh=record.description_zh,
        )

    def _record_from_raw_row(self, raw: dict[str, str], source: str) -> CatalogRecord:
        """将来源行转为统一记录 / Convert source row to common record"""
        if source == "hyg":
            return self._record_from_hyg_row(raw)
        return CatalogRecord.from_row(raw)

    def _record_from_hyg_row(self, raw: dict[str, str]) -> CatalogRecord:
        """解析 HYG 行 / Parse HYG row"""
        raw_id = raw.get("id") or raw.get("hip") or raw.get("hd") or raw.get("hr")
        if not raw_id:
            raise ValueError("missing id")
        source_id = f"hyg_{str(raw_id).strip()}"
        ra_hours = float(raw.get("ra", "0") or 0.0)
        ra_deg = (ra_hours * 15.0) % 360.0
        dec_deg = float(raw.get("dec", "0") or 0.0)
        pmra = float(raw.get("pmra", "0") or 0.0)
        pmdec = float(raw.get("pmdec", "0") or 0.0)
        mag = float(raw.get("mag", "99") or 99.0)
        proper_name = (raw.get("proper") or "").strip()
        bayer_name = (raw.get("bf") or "").strip()
        name_en = proper_name or bayer_name or source_id
        name_zh = self._COMMON_CN_NAMES.get(name_en.lower(), name_en)
        constellation = (raw.get("con") or "").strip()
        description_en = (
            f"Star {name_en}; mag={mag:.2f}; constellation={constellation or 'unknown'}."
        )
        description_zh = (
            f"恒星{name_zh}；星等={mag:.2f}；星座={constellation or '未知'}。"
        )
        return CatalogRecord(
            source_id=source_id,
            ra=ra_deg,
            dec=dec_deg,
            pmra=pmra,
            pmdec=pmdec,
            phot_g_mean_mag=mag,
            name_en=name_en,
            name_zh=name_zh,
            description_en=description_en,
            description_zh=description_zh,
        )

    def _download_file(self, url: str, target: Path) -> None:
        """下载文件，支持 urllib/curl 回退 / Download file with urllib/curl fallback"""
        try:
            urlretrieve(url, target)  # noqa: S310 - controlled by API input
            return
        except Exception:
            pass
        result = subprocess.run(
            ["curl", "-L", "--fail", "-o", str(target), url],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"下载失败 / Download failed: {result.stderr.strip() or result.stdout.strip()}"
            )

    @staticmethod
    def _gunzip_file(src: Path, dst: Path) -> None:
        """解压 gzip 文件 / Decompress gzip file"""
        import gzip
        import shutil

        with gzip.open(src, "rb") as reader, dst.open("wb") as writer:
            shutil.copyfileobj(reader, writer)

    @staticmethod
    def _sha256_of_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()


catalog_service = CatalogService()
