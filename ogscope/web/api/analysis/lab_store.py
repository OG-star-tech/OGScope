"""
星图解算实验室：清单、预设、实验记录文件存储 / Lab manifest, presets, experiment records.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ogscope.config import Settings


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AnalysisLabStore:
    """实验室侧持久化 / Lab persistence (JSON files)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.upload_root = settings.upload_dir / "analysis"
        self.presets_official = settings.data_dir / "analysis" / "presets" / "official"
        self.presets_user = settings.data_dir / "analysis" / "presets" / "user"
        self.experiments_root = settings.analysis_dir / "experiments"
        for p in (
            self.upload_root,
            self.presets_official,
            self.presets_user,
            self.experiments_root,
        ):
            p.mkdir(parents=True, exist_ok=True)

    @property
    def manifest_path(self) -> Path:
        return self.upload_root / "manifest.json"

    def load_manifest(self) -> dict[str, Any]:
        """加载上传目录清单 / Load upload manifest."""
        if not self.manifest_path.is_file():
            return {"version": 1, "entries": {}}
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "entries" not in data:
                return {"version": 1, "entries": {}}
            return data
        except Exception:
            return {"version": 1, "entries": {}}

    def save_manifest(self, data: dict[str, Any]) -> None:
        self.manifest_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def set_file_source(self, filename: str, source: str) -> None:
        """设置素材来源标签 / Set asset source tag."""
        m = self.load_manifest()
        entries: dict[str, Any] = m.setdefault("entries", {})
        ent = entries.setdefault(filename, {})
        ent["source"] = source
        ent["updated_at"] = _utc_now()
        self.save_manifest(m)

    def update_last_solve(
        self,
        filename: str,
        metrics: dict[str, Any],
    ) -> None:
        """写入最近一次解算摘要 / Cache last solve summary for list UI."""
        m = self.load_manifest()
        entries: dict[str, Any] = m.setdefault("entries", {})
        ent = entries.setdefault(filename, {})
        ent["last_solve"] = {**metrics, "at": _utc_now()}
        self.save_manifest(m)

    def remove_manifest_entry(self, filename: str) -> None:
        """从清单移除条目（删除文件后调用）/ Remove manifest row after file delete."""
        m = self.load_manifest()
        entries: dict[str, Any] = m.setdefault("entries", {})
        if filename in entries:
            del entries[filename]
            self.save_manifest(m)

    def merge_list_entry(self, filename: str, base: dict[str, Any]) -> dict[str, Any]:
        """合并清单元数据到列表项 / Merge manifest into upload list row."""
        m = self.load_manifest()
        ent = m.get("entries", {}).get(filename, {})
        row = {**base}
        if "source" in ent:
            row["source"] = ent["source"]
        else:
            row["source"] = "unknown"
        if "last_solve" in ent:
            row["last_solve"] = ent["last_solve"]
        return row

    def list_presets(self, scope: str) -> list[dict[str, Any]]:
        """列出预设 JSON / List preset files."""
        root = self.presets_official if scope == "official" else self.presets_user
        out: list[dict[str, Any]] = []
        if not root.is_dir():
            return out
        for p in sorted(root.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data.setdefault("id", p.stem)
                    data.setdefault("scope", scope)
                    out.append(data)
            except Exception:
                continue
        return out

    def save_user_preset(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        """保存用户预设 / Save user preset."""
        pid = str(uuid.uuid4())
        payload = {
            "id": pid,
            "name": name,
            "scope": "user",
            "params": params,
            "created_at": _utc_now(),
        }
        target = self.presets_user / f"{pid}.json"
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return payload

    def delete_user_preset(self, preset_id: str) -> None:
        """删除用户预设 / Delete user preset."""
        clean = Path(preset_id).name
        target = self.presets_user / f"{clean}.json"
        if target.is_file():
            target.unlink()

    def create_experiment(
        self,
        input_name: str,
        preset_label: str,
        result_json: dict[str, Any],
        metrics: dict[str, Any],
        thumbnail_png_base64: str | None,
        replay: dict[str, Any] | None = None,
        save_asset_snapshot: bool = True,
    ) -> dict[str, Any]:
        """写入实验记录 / Persist experiment record."""
        eid = str(uuid.uuid4())
        thumb_path: str | None = None
        if thumbnail_png_base64:
            raw = base64.b64decode(
                thumbnail_png_base64.split(",")[-1]
                if "," in thumbnail_png_base64
                else thumbnail_png_base64
            )
            thumb_path = str(self.experiments_root / f"{eid}.png")
            Path(thumb_path).write_bytes(raw)
        asset_snapshot_relpath: str | None = None
        asset_digest: str | None = None
        src = (self.upload_root / Path(input_name).name).resolve()
        root = self.upload_root.resolve()
        if (
            save_asset_snapshot
            and src.is_file()
            and str(src).startswith(str(root))
        ):
            try:
                data = src.read_bytes()
                asset_digest = hashlib.sha256(data).hexdigest()
                ext = src.suffix if src.suffix else ".bin"
                asset_snapshot_relpath = f"{eid}_asset{ext}"
                (self.experiments_root / asset_snapshot_relpath).write_bytes(data)
            except OSError:
                asset_snapshot_relpath = None
                asset_digest = None
        rec = {
            "id": eid,
            "input_name": input_name,
            "preset_label": preset_label,
            "created_at": _utc_now(),
            "metrics": metrics,
            "result_json": result_json,
            "thumbnail_relpath": Path(thumb_path).name if thumb_path else None,
            "replay": replay,
            "asset_snapshot_relpath": asset_snapshot_relpath,
            "asset_digest": asset_digest,
        }
        (self.experiments_root / f"{eid}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return rec

    def delete_experiment(self, experiment_id: str) -> None:
        """删除一条实验记录 JSON、缩略图与素材快照 / Delete experiment artifacts."""
        clean = Path(experiment_id).name
        if not clean or clean != experiment_id.strip():
            raise ValueError("实验 ID 无效 / Invalid experiment id")
        jpath = self.experiments_root / f"{clean}.json"
        if not jpath.is_file():
            raise FileNotFoundError("实验记录不存在 / Experiment not found")
        try:
            data = json.loads(jpath.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        snap = data.get("asset_snapshot_relpath")
        jpath.unlink()
        thumb = self.experiments_root / f"{clean}.png"
        if thumb.is_file():
            thumb.unlink()
        if isinstance(snap, str) and snap:
            sp = (self.experiments_root / Path(snap).name).resolve()
            er = self.experiments_root.resolve()
            if str(sp).startswith(str(er)) and sp.is_file():
                sp.unlink()

    def count_experiments_for_input(self, input_name: str) -> int:
        """统计引用某素材文件名的实验条数 / Count experiments for an upload basename."""
        base = Path(input_name).name
        n = 0
        for r in self._all_experiment_records():
            if (r.get("input_name") or "") == base:
                n += 1
        return n

    def delete_experiments_for_input(self, input_name: str) -> int:
        """删除所有引用该素材的实验记录 / Cascade-delete experiments by input filename."""
        base = Path(input_name).name
        ids = [
            str(r.get("id"))
            for r in self._all_experiment_records()
            if (r.get("input_name") or "") == base and r.get("id")
        ]
        for eid in ids:
            try:
                self.delete_experiment(eid)
            except (FileNotFoundError, ValueError):
                continue
        return len(ids)

    def experiment_asset_path(self, experiment_id: str) -> Path:
        """实验素材快照文件路径 / Path to snapshot copy for replay."""
        clean = Path(experiment_id).name
        jpath = self.experiments_root / f"{clean}.json"
        if not jpath.is_file():
            raise FileNotFoundError("实验记录不存在 / Experiment not found")
        data = json.loads(jpath.read_text(encoding="utf-8"))
        rel = data.get("asset_snapshot_relpath")
        if not rel:
            raise FileNotFoundError("无素材快照 / No asset snapshot for this record")
        p = (self.experiments_root / Path(str(rel)).name).resolve()
        er = self.experiments_root.resolve()
        if not str(p).startswith(str(er)) or not p.is_file():
            raise FileNotFoundError("快照文件不存在 / Snapshot missing")
        return p

    def _all_experiment_records(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for p in sorted(
            self.experiments_root.glob("*.json"),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        ):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    rows.append(data)
            except Exception:
                continue
        return rows

    def list_experiments(
        self,
        q: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        """分页列出实验 / Paginated experiment list."""
        rows = self._all_experiment_records()
        if q:
            ql = q.lower()
            rows = [
                r
                for r in rows
                if ql in (r.get("input_name") or "").lower()
                or ql in (r.get("preset_label") or "").lower()
            ]
        total = len(rows)
        start = max(0, (page - 1) * page_size)
        end = start + page_size
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": rows[start:end],
        }

    def export_experiments_json(self) -> str:
        """导出全部实验为 JSON 字符串 / Export all as JSON."""
        rows = self._all_experiment_records()
        return json.dumps(rows, ensure_ascii=False, indent=2)

    def export_experiments_csv(self) -> str:
        """导出 CSV / Export CSV."""
        items = self._all_experiment_records()
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(
            [
                "id",
                "created_at",
                "input_name",
                "preset_label",
                "matches",
                "rmse_arcsec",
            ]
        )
        for r in items:
            m = r.get("metrics") or {}
            w.writerow(
                [
                    r.get("id"),
                    r.get("created_at"),
                    r.get("input_name"),
                    r.get("preset_label"),
                    m.get("matches", ""),
                    m.get("rmse_arcsec", ""),
                ]
            )
        return buf.getvalue()
