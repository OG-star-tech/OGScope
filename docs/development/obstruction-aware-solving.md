# 遮挡感知星图解算 / Obstruction-aware Plate Solving

## 目标 / Goal

提高楼宇、树枝、电线、月亮或强光进入画面时的解算恢复率，同时保证银河、疏散星团等高密度星场不会仅因星点多而被误判。

Improve recovery when buildings, branches, wires, the Moon, or bright lights enter the frame, while ensuring that rich Milky Way fields and open clusters are never classified as obstruction merely because they contain many stars.

## 第一版流程 / Version-one Flow

1. Tetra3 正常提星并使用亮度最高的 `max_stars` 个候选进行常规解算。
2. 常规解算成功时立即返回；不运行画面分类，也不允许分类推翻结果。
3. 常规解算失败时，在长边不超过 320 像素的缩小图上寻找两类独立证据：大面积高亮连通域、跨越一定画幅尺度的长结构边缘。
4. 没有独立结构证据时直接保留常规失败结果。星点数量、局部星点密度以及“看起来复杂”都不能独立触发过滤。
5. 有结构证据时，仅剔除同时满足几何异常（局部过密或强共线）且落在结构证据范围内的候选，再使用后备候选补位并重试一次。
6. 单次最多剔除候选池的 35%，并始终保留至少四个候选；达到上限时设置 `CENTROID_FILTER_LIMITED` 并保守放行其余候选。

1. Tetra3 performs normal extraction and solves with the brightest `max_stars` candidates.
2. A normal match returns immediately. Scene classification does not run and cannot overturn it.
3. After a normal failure, a downscaled image with a maximum side of 320 pixels is checked for two independent signals: large bright connected regions and long structural edges spanning a meaningful part of the frame.
4. Without independent structural evidence, the normal failure is retained. Candidate count, local star density, or general visual complexity cannot trigger filtering alone.
5. With structural evidence, only geometrically abnormal candidates (locally dense or strongly collinear) that overlap the evidence are removed. Reserve candidates fill the released slots and one retry is made.
6. A retry removes at most 35% of the reserve pool and always retains at least four candidates. Reaching the cap emits `CENTROID_FILTER_LIMITED` and fails open for the rest.

## 性能边界 / Performance Boundary

- 正常成功路径只多保留一个有界后备候选池，不运行 OpenCV 场景分析。
- 场景分析使用缩小图，像素工作量与相机原始分辨率解耦。
- 仅在“常规失败 + 有结构证据 + 候选集合实际变化”时增加第二次 Tetra3 解算。
- `centroid_quality.scene.metrics.analysis_ms` 记录分析耗时，便于在 Raspberry Pi Zero 2W 上做真实验收。

- The normal success path keeps only a bounded reserve pool and does not run OpenCV scene analysis.
- Scene analysis runs on a small image, decoupling its pixel cost from camera resolution.
- A second Tetra3 solve occurs only after a normal failure, structural evidence, and an actual candidate-set change.
- `centroid_quality.scene.metrics.analysis_ms` records the cost for real Raspberry Pi Zero 2W acceptance.

## 已知边界与验收 / Known Limits and Acceptance

第一版是保守的经典视觉方法，不声称理解物体类别。真实设备验收至少覆盖：无障碍普通星场、银河或疏散星团密集星场、树枝、电线/屋檐、月亮/强光，以及遮挡与星场混合画面。算法测试通过只代表代码验证，不能替代夜间实拍的连续解算成功率、误过滤率和延迟验收。

Version one is a conservative classical-vision method and does not claim semantic object recognition. Device acceptance should cover unobstructed fields, rich Milky Way or open-cluster fields, branches, wires/rooflines, the Moon/bright lights, and mixed obstruction-plus-stars scenes. Passing algorithm tests proves code behavior only; it does not replace nighttime validation of repeated solve rate, false-filter rate, and latency.
