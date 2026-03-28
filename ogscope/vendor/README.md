# Vendored cedar-solve (`tetra3`)

本目录为 **[cedar-solve](https://github.com/smroid/cedar-solve)** 仓库中的 `tetra3` 包完整拷贝（与 PyPI [`cedar-solve`](https://pypi.org/project/cedar-solve/) 同源），便于离线部署与锁定版本；**非自研解算算法**。

This folder is the upstream **`tetra3`** package from cedar-solve (same family as PyPI `cedar-solve`), vendored for offline boards — **not a reimplementation**.

- 许可证 / License: [tetra3/LICENSE.txt](tetra3/LICENSE.txt)（Apache-2.0）
- `tetra3/data/default_database.npz` 体积大，不随 Git 提交；请从 cedar-solve 源码包复制到 `data/plate_solve/` 或 `tetra3/data/` / Large `default_database.npz` is not committed; copy from cedar-solve release or your `cedar-solve-master/tetra3/data/`.
