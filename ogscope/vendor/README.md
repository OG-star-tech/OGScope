# Vendored tetra3 (Cedar-Solve)

本目录包含从 [cedar-solve](https://github.com/smroid/cedar-solve) 抽取的核心 `tetra3` 模块，以兼容项目中的 NumPy 2.x 与 Pillow 10+（上游 PyPI 包约束较旧）。

- 许可证：见 [tetra3/LICENSE.txt](tetra3/LICENSE.txt)（Apache-2.0）
- 数据文件 `default_database.npz` 不随仓库提供，请放到 `data/plate_solve/` 或配置 `OGSCOPE_SOLVER_TETRA_DATABASE_PATH`
