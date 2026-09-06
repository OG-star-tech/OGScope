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

## 混合明暗遮挡增强 / Mixed-Luminance Obstruction Enhancement

当亮树与暗树同时进入画面时，绝对高亮阈值和全局边缘阈值可能只覆盖亮侧。失败路径因此增加两个有界的局部暗结构尺度：先抑制点状星像，再从局部背景中寻找具有足够面积和跨度的负向对比结构。检测结果以 `DARK_EXTENDED_STRUCTURE` 和 `dark_structural_region` 输出，不把“暗”本身视为遮挡证据。

达到 35% 保守剔除上限时，额度在相互独立的证据连通域之间轮询分配。这样亮区中排位靠前的假星不会耗尽全部额度，暗结构附近的候选仍有机会被替换。总上限、至少四点、独立结构证据与单次回退约束保持不变。

When bright and dark trees share a frame, absolute brightness and global edge thresholds may cover only the bright side. The failure path therefore adds two bounded local dark-structure scales: point-like stars are suppressed first, then negative-contrast components must pass both area and span gates. Results are exposed as `DARK_EXTENDED_STRUCTURE` and `dark_structural_region`; darkness alone is never obstruction evidence.

When the conservative 35% rejection cap is reached, its budget is distributed round-robin across independent evidence components. Bright, early-ranked clutter can no longer consume the whole cap before candidates near dark structures are considered. The total cap, four-point minimum, independent-evidence requirement, and single-retry boundary remain unchanged.

## 性能边界 / Performance Boundary

- 正常成功路径只多保留一个有界后备候选池，不运行 OpenCV 场景分析。
- 场景分析使用缩小图，像素工作量与相机原始分辨率解耦。
- 仅在“常规失败 + 有结构证据 + 候选集合实际变化”时增加第二次 Tetra3 解算。
- `centroid_quality.scene.metrics.analysis_ms` 记录分析耗时，便于在 Raspberry Pi Zero 2W 上做真实验收。

- The normal success path keeps only a bounded reserve pool and does not run OpenCV scene analysis.
- Scene analysis runs on a small image, decoupling its pixel cost from camera resolution.
- A second Tetra3 solve occurs only after a normal failure, structural evidence, and an actual candidate-set change.
- `centroid_quality.scene.metrics.analysis_ms` records the cost for real Raspberry Pi Zero 2W acceptance.
- 暗结构检测只保留 320 像素分析图、逐尺度复用的灰度残差与小尺寸区域标签，不增加模型权重或 JPEG 编码。
- Dark-structure detection keeps only the 320-pixel analysis image, a grayscale residual reused across scales, and a compact region-label map; it adds no model weights or JPEG encoding.

## 已知边界与验收 / Known Limits and Acceptance

该能力是保守的经典视觉方法，不声称理解物体类别。真实设备验收至少覆盖：无障碍普通星场、银河或疏散星团密集星场、树枝、电线/屋檐、月亮/强光、亮暗树木同时出现，以及遮挡与星场混合画面。算法测试通过只代表代码验证，不能替代夜间实拍的连续解算成功率、误过滤率和延迟验收。

This remains a conservative classical-vision method and does not claim semantic object recognition. Device acceptance should cover unobstructed fields, rich Milky Way or open-cluster fields, branches, wires/rooflines, the Moon/bright lights, mixed bright/dark trees, and obstruction-plus-stars scenes. Passing algorithm tests proves code behavior only; it does not replace nighttime validation of repeated solve rate, false-filter rate, and latency.
