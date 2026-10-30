# Core 相机发布冒烟 / Core Camera Release Smoke

此流程把相机启动、真实预览字节、分析与重复停止串成可复现的 Core API 检查。自动通过只证明所测链路，发布仍需人工验收；本次工具提交不代表已完成板上验证。

This workflow exercises camera start, preview bytes, analysis and repeated stops through Core. Automated success covers only the exercised path; release requires manual acceptance. Adding this tool is not evidence of a board run.

## 运行前 / Before Running

在维护窗口运行，先让产品、浏览器预览、分析和录像退出。脚本遇到已有消费者会终止；预检到写操作之间仍存在竞争窗口，运行期间应独占设备。脚本不切网络、不改相机参数、不删除文件，也不执行 systemd 操作。

Use an exclusive maintenance window with product sessions, browser previews, analysis and recording closed. Preflight refuses observed consumers, but it is not an atomic maintenance lock. The tool does not switch networks, tune settings, delete files or operate systemd.

先独立核对 systemd 运行目录、生效配置、部署回执与实际服务版本。设置 `DEPLOYED_COMMIT` 为已经确认部署的完整 40 位 SHA。不能直接把客户端目录的 `git rev-parse HEAD` 当成服务 commit；当前 API 不报告 commit。报告明确将 SHA 与 profile 标记为人工提供、未经 API 证明。

Independently confirm the systemd working directory, effective configuration, deployment receipt and running version. Set `DEPLOYED_COMMIT` to the confirmed deployed 40-character SHA. A client's checkout SHA does not establish the running service commit. The API does not expose commit identity, so the report marks commit/profile as operator supplied.

先执行 GET 预检，再显式授权相机及分析启停：

Run GET preflight first, then explicitly authorize camera and analysis control:

```bash
python3 scripts/core-api-smoke.py \
  --expected-backend v4l2 --service-commit "$DEPLOYED_COMMIT" \
  --profile compatibility --dry-run --json \
  --output /tmp/ogscope-core-preflight.json

python3 scripts/core-api-smoke.py \
  --expected-backend v4l2 --service-commit "$DEPLOYED_COMMIT" \
  --profile compatibility --yes --json \
  --output /tmp/ogscope-core-smoke.json
```

Picamera2 使用 `--expected-backend imx327_mipi --profile picamera2`；严格 ISP 使用 `v4l2 --profile isp`，并人工检查 `info.image_processing.effective` 的真实回读。profile 是记录标签，不会切换配置或证明 ISP 已生效。仅允许两个物理后端标签，模拟结果不能充当板上证据。`--dry-run` 仅使用 GET 预检，不启动捕获或分析。

Use `imx327_mipi --profile picamera2` for Picamera2. Use `v4l2 --profile isp` for strict ISP and independently verify actual `info.image_processing.effective`. Profile labels neither change configuration nor prove ISP processing. Simulation is not board evidence. Dry-run uses GET preflight without starting capture or analysis.

## 自动检查范围 / Automated Scope

1. `/health`、Core 系统版本、预期后端、无消费者与无运行分析。进程健康不等于相机健康；初始 Core health 单独记录。/ Check process health, Core version, expected backend and observed idle ownership. Record Core health separately.
2. 获取 120 秒相机租约，启动相机，验证 `applied.ready`；读取并立即关闭一路 MJPEG，检查一张 JPEG 的完整起止标记。该步骤不评价画质或星图精度。/ Acquire a bounded lease, require confirmed start, read a JPEG marker-complete MJPEG frame and close the stream. This does not assess image quality or solve accuracy.
3. 使用随机 owner 启动分析，续期租约与会话，等待一次完整解算结果。允许 `MATCH_FOUND`、`NO_MATCH`、`TOO_FEW`、`TIMEOUT`，暗场没有星图不等于链路故障；数据库、提星或准备错误会失败。/ Use a random owner and renew both leases while waiting for one solve. Scene outcomes may include no match, too few stars or solve timeout; database, extraction and preparation errors fail.
4. 按 owner 与 session 条件停止本次分析，释放租约，停止相机并检查无消费者、`streaming=false`、`phase=sleeping`；默认循环两次。仅流状态为 false 不能证明原句柄已释放。/ Conditionally stop only this analysis, release its lease, stop capture and verify sleeping phase, stopped streaming and zero consumers; repeat twice by default. Stopped streaming alone does not prove release of the original handle.

每次 HTTP 请求默认预算 45 秒，分析观察预算 60 秒；`--timeout`、`--wait` 可调，单次在途请求最多额外占用一个 HTTP 预算。没有自动重试启动、停止或恢复服务。失败后尽力按 owner/session 清理、释放租约；停止请求失败不会再次自动停止。清理不确定时应人工检查，不强制终止其他任务。

HTTP requests default to 45 seconds and analysis observation to 60 seconds; one in-flight request can add up to an HTTP budget. Start, stop and service recovery are not automatically retried. Failure triggers conditional cleanup and lease release; a failed camera-stop request is not repeated. Inspect uncertain cleanup manually without force-stopping another task.

## 报告与发布判断 / Report and Release Decision

JSON 包含时间、服务版本、角色、人工声明的 commit/profile、API 回读后端、逐项检查、人工项目及 `release_allowed`。不会保存 owner token、原始图片或完整环境配置。报告属于设备验证证据，默认保存在仓库外。

JSON records timestamps, service version, role, declared commit/profile, reported backend, individual checks and manual items. Owner tokens, images and full environment files are omitted. Save device receipts outside the repository.

| 退出码 / Exit | 含义 / Meaning | 发布判断 / Release |
|---|---|---|
| 0 | 自动链路通过 / Automated path passed | `manual_acceptance_required`，`release_allowed=false` |
| 2 | 参数或缺少 `--yes` / Invalid arguments or missing explicit control authorization | 未运行 / Not run |
| 4 | 检查或清理失败 / Check or cleanup failed | `blocked` |
| 5 | 仅 GET 预检 / GET preflight only | 不完整，不能发布 / Incomplete |

自动通过后，由维护者附上以下证据并明确给出 go/no-go：

After automated success, the maintainer attaches the following evidence and records an explicit go/no-go:

- 实际服务 commit、生效配置、相机后端与部署模板一致。/ Running commit, effective configuration, backend and deployment profile agree.
- 长曝光中停止、启动失败恢复、预览/分析/录像竞争及另一调用方停止请求符合现有保护。/ Verify long-exposure stop, failed-start recovery, competing consumers and another caller's stop request.
- 在同一版本上人工重启服务后重新执行本工具，单独保存重启前后两份报告。/ Manually restart the service and rerun the tool at the same revision; save both receipts separately.
- 持续预览并发解算的 CPU、PSS、swap、CMA、OOM、过期帧；方向、RGB、FOV；真实星空精度另行验收。/ Inspect sustained resource behavior, stale frames, orientation, RGB and FOV; accept real-sky accuracy separately.
- 失败时保留报告与日志，检查是否需人工重启服务或回退；不因自动测试通过宣称已完成发布验收。/ Retain failure evidence and assess service restart or rollback manually; automated success alone never establishes release acceptance.

复用 [V4L2 板上脚本](../../scripts/validate_v4l2_zero2w.py) 诊断驱动，结合[相机部署验收](camera-deployment-profiles.md)。驱动脚本的重复开关不能替代服务级验证。

Reuse the V4L2 board script for driver diagnosis together with camera deployment acceptance. Driver-only restart cycles do not replace service-level checks.
