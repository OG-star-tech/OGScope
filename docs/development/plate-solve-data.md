# 星空解算数据维护方案 / Plate solve data maintenance

本文说明 OGScope 在移除 SQLite/HYG 星表后，**仅依赖 Tetra3（Cedar-Solve）图案库** `default_database.npz` 的部署、备份与排障。

## 1. 数据形态 / What the file is

- **不是**关系型数据库：无 `stars.db`、无 HYG CSV 索引。
- **`default_database.npz`** 为 NumPy 压缩归档，内含：
  - 预计算的 **四星图案哈希表**（用于 lost-in-space 匹配）
  - **星表向量**（球面 KD 树等），与构建时所用的 Hipparcos/Tycho/BSC 等相关
- 运行时由 `tetra3.Tetra3` 加载到内存；解算结果中的 `tetra` 字段会附带 Tetra 原始输出（含 `status`、`Matches`、`RMSE` 等）。

源码中 vendored 包位置：`ogscope/vendor/tetra3/`（Apache-2.0，见 `ogscope/vendor/tetra3/LICENSE.txt`）。

## 2. 获取图案库文件 / Obtaining `default_database.npz`

任选其一：

1. **从 PyPI `cedar-solve` wheel 提取**  
   安装 wheel 后，在 site-packages 中查找 `tetra3/data/default_database.npz`，复制到 `data/plate_solve/`。
2. **自行生成**（换 FOV、极限星等时）  
   使用 `tetra3.Tetra3.generate_database()`，并按上游文档准备 `hip_main` / `tyc_main` / `BSC5` 等星表文件（生成耗时可能很长）。

## 3. 配置与部署 / Configuration

| 方式 | 说明 |
|------|------|
| 默认 | 若存在 `data/plate_solve/default_database.npz`，优先通过配置解析为该路径 |
| `OGSCOPE_PLATE_SOLVE_DIR` | 图案库目录（默认 `./data/plate_solve`） |
| `OGSCOPE_SOLVER_TETRA_DATABASE_PATH` | `default_database.npz` 的**绝对路径**（最高优先级） |

应用配置项见 `ogscope/config.py`：`plate_solve_dir`、`solver_tetra_database_path`、`solver_fov_deg`、`solver_fov_max_error_deg`、`solver_timeout_ms`。

**systemd** 部署时：将 `WorkingDirectory` 设为项目根，并确保 `data/plate_solve/default_database.npz` 存在或环境变量指向设备上可读路径。

## 4. 版本与备份 / Versioning and backup

- 在 `poetry.lock` 或发行说明中**记录**与 `ogscope/vendor/tetra3` 对齐的 Cedar-Solve / Tetra3 版本思路（当前为 vendored 快照）。
- **备份**：对生产用 `default_database.npz` 保留副本（可按文件大小 + SHA256 校验）。
- **升级**：替换 `.npz` 后重启服务；建议在板子上用调试页上传测试图验证 `status: MATCH_FOUND`。

## 5. 与旧方案关系 / Migration from SQLite catalog

- 已移除：`/api/catalog`、`HYG` 下载、`stars.db`、调试页星表 CRUD。
- 解算置信度不再来自「本地星表密度」，而来自 Tetra 的 `Prob`、`Matches`、`RMSE` 等。

## 6. 故障排查 / Troubleshooting

| 现象 | 可能原因 | 处理 |
|------|-----------|------|
| `DATABASE_ERROR` / 无法加载 | `.npz` 缺失或路径错误 | 检查文件与 `OGSCOPE_SOLVER_TETRA_DATABASE_PATH` |
| `TOO_FEW` | 检出星点 &lt; 4 | 曝光/阈值、减少云与前景光 |
| `NO_MATCH` / `TIMEOUT` | FOV 与库不匹配、假星多 | 调整 `solver_fov_deg`、星点提取、`solve_timeout_ms` |
| 窄视场长期失败 | 默认库偏 10°–30° 一类 | 使用 `generate_database` 生成匹配 FOV 的库 |

## 7. 性能提示 / Performance

- Orange Pi 等资源受限设备：可适当**降低分辨率**、限制 `solver_max_stars`、拉大 `solver_fullsolve_interval_frames`（实时模式）。
- Tetra 解算在后台线程执行，避免阻塞事件循环（见 `asyncio.to_thread`）。
