"""
星表管理路由 / Catalog management routes
"""

from fastapi import APIRouter, HTTPException, Query

from ogscope.web.api.catalog.services import CatalogApiService
from ogscope.web.api.models.schemas import (
    CatalogBuildIndexRequest,
    CatalogDownloadRequest,
    CatalogStarUpsertRequest,
)

router = APIRouter()


@router.post("/catalog/download")
async def download_catalog(payload: CatalogDownloadRequest):
    """下载星表 / Download catalog"""
    try:
        return await CatalogApiService.download_catalog(
            source=payload.source,
            url=payload.url,
            magnitude_limit=payload.magnitude_limit,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/catalog/build-index")
async def build_catalog_index(payload: CatalogBuildIndexRequest):
    """构建索引 / Build index"""
    try:
        return await CatalogApiService.build_index(
            magnitude_limit=payload.magnitude_limit,
            ra_bin_size_deg=payload.ra_bin_size_deg,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/catalog/status")
async def get_catalog_status():
    """获取状态 / Get status"""
    try:
        return await CatalogApiService.get_status()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/catalog/stars")
async def list_catalog_stars(
    limit: int = Query(default=100, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    source_query: str | None = Query(default=None),
    min_mag: float | None = Query(default=None),
    max_mag: float | None = Query(default=None),
):
    """分页查询星点 / List stars"""
    try:
        return await CatalogApiService.list_stars(
            limit=limit,
            offset=offset,
            source_query=source_query,
            min_mag=min_mag,
            max_mag=max_mag,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/catalog/stars/{source_id}")
async def get_catalog_star(source_id: str):
    """读取星点详情 / Get star details"""
    try:
        return await CatalogApiService.get_star(source_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/catalog/stars")
async def create_catalog_star(payload: CatalogStarUpsertRequest):
    """新增星点 / Create star"""
    try:
        return await CatalogApiService.create_star(payload.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/catalog/stars/{source_id}")
async def update_catalog_star(source_id: str, payload: CatalogStarUpsertRequest):
    """更新星点 / Update star"""
    try:
        update_payload = payload.model_dump()
        update_payload["source_id"] = source_id
        return await CatalogApiService.update_star(source_id, update_payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/catalog/stars/{source_id}")
async def delete_catalog_star(source_id: str):
    """删除星点 / Delete star"""
    try:
        return await CatalogApiService.delete_star(source_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
