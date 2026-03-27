"""
星表管理服务 / Catalog management services
"""

from __future__ import annotations

from typing import Any

from ogscope.data.catalog.service import catalog_service


class CatalogApiService:
    """星表 API 服务 / Catalog API service"""

    @staticmethod
    async def download_catalog(
        source: str, url: str | None, magnitude_limit: float
    ) -> dict[str, Any]:
        return catalog_service.download_catalog(
            source=source, url=url, magnitude_limit=magnitude_limit
        )

    @staticmethod
    async def build_index(
        magnitude_limit: float, ra_bin_size_deg: float
    ) -> dict[str, Any]:
        return catalog_service.build_index(
            magnitude_limit=magnitude_limit, ra_bin_size_deg=ra_bin_size_deg
        )

    @staticmethod
    async def get_status() -> dict[str, Any]:
        return catalog_service.get_status()

    @staticmethod
    async def list_stars(
        limit: int,
        offset: int,
        source_query: str | None,
        min_mag: float | None,
        max_mag: float | None,
    ) -> dict[str, Any]:
        return catalog_service.list_stars(
            limit=limit,
            offset=offset,
            source_query=source_query,
            min_mag=min_mag,
            max_mag=max_mag,
        )

    @staticmethod
    async def get_star(source_id: str) -> dict[str, Any]:
        row = catalog_service.get_star(source_id)
        if not row:
            raise FileNotFoundError("星点不存在 / Star not found")
        return row

    @staticmethod
    async def create_star(payload: dict[str, Any]) -> dict[str, Any]:
        return catalog_service.create_star(payload)

    @staticmethod
    async def update_star(source_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return catalog_service.update_star(source_id, payload)

    @staticmethod
    async def delete_star(source_id: str) -> dict[str, Any]:
        deleted = catalog_service.delete_star(source_id)
        if not deleted:
            raise FileNotFoundError("星点不存在 / Star not found")
        return {"success": True, "source_id": source_id}
