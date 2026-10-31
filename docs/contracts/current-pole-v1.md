# 当前极轴契约 / Current pole contract

OGScope owns the astronomical model, observing policy, camera attitude and polar target. Consumers retain mechanical planning and calibration only. OGScope 统一负责天文模型、观测策略、相机姿态与极轴目标；调用方只负责机械规划与校准。

- `astronomy.policy=current_pole_v1` is the product and developer-analysis default; legacy Core v1 requests that omit the new field retain their historical semantics; `catalog_visual_v1` is an explicit historical diagnostic baseline. 默认使用当前极轴，历史星库极点仅作为显式诊断基线。
- `target_pole=north|south` selects the physical pole and is frozen for an analysis session. 会话冻结南北极身份；重复启动不得修改目标、观测地点或天文策略。
- Raw RA/Dec/Roll, catalogue epoch, matched stars and frame identity retain their original meanings. 原始解算、匹配星点和帧身份不被天文转换覆盖。
- `astronomy` in each result reports validity, actual corrections, exposure UTC, site, environmental assumptions, model and fitted attitude. 每帧报告实际生效策略、曝光时间、地点、环境假设、模型与姿态。
- `overlay_ext.polar_guide` is generated from that same fitted attitude and physical pole. It reports angular error and a pinhole/distortion-aware pixel target. 图像引导、角距离与像素目标来自同一姿态和物理极轴。
- Camera basis columns are **image left, image up, optical axis**; local axes are east, north, up (ENU). Pixel offsets are right/down positive. 相机基向量依次为图像左、图像上、光轴；当地坐标为东、北、天；像素偏移右、下为正。

## Model and inputs / 模型与输入

ERFA uses IAU 2006/2000A precession/nutation, annual and diurnal aberration, solar deflection and Earth rotation. Matched catalogue stars are transformed before fitting camera attitude, including optional field-dependent refraction. 使用 ERFA 标准岁差章动、周年及周日光行差、太阳光偏折与地球自转模型；先变换匹配恒星，再拟合姿态，折射开启时逐星计算。

Catalogue equinox must be explicitly 2000.0; positions are treated as ICRS-oriented J2000 catalogue directions. Catalogue proper-motion epoch is retained, but missing stellar proper motions/parallaxes are not invented. 必须有明确的 J2000 星库历元；保留自行历元，不虚构星体自行或视差。

UTC is the exposure midpoint, never the result retrieval time. External trusted clocks may calibrate the acquisition clock once at session start; a source-authoritative exposure timestamp is never shifted. File analysis requires an explicit observation time. UTC 使用曝光中点；可信外部时钟可在会话开始时校准采集时钟，来源权威时间不得二次偏移；文件解算必须提供拍摄时间。

Developer camera analysis freezes exposure metadata before solving, just as Core does. A wall-clock step relative to the monotonic clock makes the target unavailable; a later camera exposure must not retime an earlier image. 开发相机入口与 Core 一样在解算前冻结曝光信息；系统时钟跳变时目标不可用，后续曝光参数不得改写旧图像时刻。

`solve_context.observer` supplies latitude, longitude and altitude; time quality is declared in `solve_context.quality`. Without a site, current-pole image guidance is available in CIRS; local attitude is unavailable. 缺少地点时可以生成 CIRS 下的当日极轴图像引导，但不得声称已有当地姿态。

`astronomy.refraction.mode` is `off` (default), `standard`, or `measured`. Standard mode estimates pressure from altitude and declares its temperature/humidity assumptions. Measured mode requires pressure and temperature; humidity and wavelength defaults are explicit. Below 5 degrees, enabled refraction is unavailable. 折射默认关闭；标准模式明确标记海拔估压等假设；实测模式要求气压、温度；低于 5 度不提供已修正目标。

Standard mode accepts optional `temperature_c` (-80…60°C). Omitted/null uses 10°C; zero is a real 0°C input. Pressure remains estimated from known site altitude, never from CPU temperature. The receipt distinguishes `pressure_source=altitude_estimate` from `measured`, and `temperature_source=standard|manual|measured|unused`. The requested values, including an explicit temperature, are frozen with the session and must match the consumer acknowledgement.
标准模式允许手填环境气温（-80…60°C）；省略或 null 使用 10°C，0 表示实际填写 0°C。气压仍按有效地点海拔估算，不使用 CPU 温度；逐帧回执区分海拔估压、标准温度、手填温度和实测来源。请求参数与会话一起冻结，消费方须核对启动确认。

Missing altitude stays unknown (`observer.altitude_m=null`), distinct from measured sea level (`0`). Requested standard refraction then returns `refraction_requires_altitude` without an actionable target. Refraction off remains usable; its geometric observer-height approximation is zero when altitude is unknown. Measured-pressure mode does not require an altitude estimate. Latitude/longitude and finite altitude bounds (-500…10000 m when supplied) are still validated.
海拔缺失保持未知，与真实 0 米区分；开启标准折射时返回 `refraction_requires_altitude`，不输出可用于运动的目标。关闭折射仍可使用，未知海拔仅在几何计算中暂按零近似；实测气压模式无需估压海拔。地点及已提供海拔仍须通过有限数与范围校验。

UT1−UTC is initially approximated as zero and polar motion is omitted, both reported in the result. Catalogue/proper-motion, lens calibration and atmospheric uncertainties remain outside numerical model validation. 初版明确记录 UT1 与 UTC 近似相等、未应用极移；星库自行、镜头及大气误差不能由数值测试替代验收。

## Failure and compatibility / 失败与兼容

A valid star match can coexist with an unavailable polar target. Missing time, unsupported epoch, insufficient matched geometry or unavailable requested refraction produces a reason code and no actionable guide. 不完整的观测条件不得把成功星图匹配伪装成有效极轴目标；失败保留原始解算，返回原因码。

Consumers must negotiate `capabilities.current_pole_target`, verify start acknowledgement and per-frame policy/pole/frame identity, and reject stale or incompatible targets. No silent local astronomy or fallback to the J2000 pole is allowed. 调用方校验能力、启动确认及逐帧身份；不允许静默本地补算或退回旧极点。

## Affected consumers / 影响范围

Consumers must retain target policy, observer and frame identity whenever they use, store or display a target. 调用方使用、保存或显示目标时，必须保留策略、观测条件与帧身份。

Previously stored references without astronomical provenance require explicit revalidation before reuse. 缺少天文来源的历史参考在复用前需要明确重新验证。

Numerical references, independently generated star fields through the actual solver, consumer contract tests and physical mechanical-axis acceptance are separate verification layers. 标准数值、独立星图经真实解算器、消费方契约及实机机械极轴分别验收。

OGScope owns numerical, solver and Core API regressions. External applications own their integration suites, application workflows and physical acceptance. OGScope 维护数值、解算器与 Core API 回归；外部应用自行维护集成测试、业务流程及实机验收。

## Parallel integration / 并行集成

OGScope #24 adds southern pole selection to the legacy guide. This change includes that additive selection contract and extends it to current-pole fits; reconcile #24 without restoring the legacy product default. OGScope #22 changes realtime capture scheduling: preserve its frame/time lifecycle and compute astronomy once per published solve. #24 的南北极选择与本次有重叠；#22 的采集生命周期须保留，禁止在读取结果时重算目标。

The physical target is the modelled celestial intermediate pole (CIP), not a weather-dependent apparent star position. Sub-arcsecond Earth orientation and measured-weather accuracy require separate acceptance. 目标为模型中的天球中间极；光行差、折射作用于恒星观测方向，不改变物理轴定义。

## Standards / 标准依据

- [IAU SOFA precession/nutation guide](https://www.iausofa.org/s/sofa_pn_c.pdf): reference-frame transformations and CIP / 参考系变换与天球中间极。
- [ERFA test vectors](https://github.com/liberfa/erfa/blob/master/src/t_erfa_c.c): fixed IAU 2006/2000A numerical reference / 标准数值参考。
- [Astropy AltAz model notes](https://docs.astropy.org/en/stable/api/astropy.coordinates.AltAz.html): pressure, temperature, humidity, wavelength and low-altitude limits / 环境参数与低高度局限。
