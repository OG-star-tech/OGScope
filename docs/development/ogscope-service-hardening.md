# OGScope 服务稳定性与内存防护 / Service stability and memory guard

## systemd 建议（示例，按板子内存调整）/ systemd suggestions (tune MemoryMax per board)

在单元文件 `[Service]` 段可考虑：

- `Restart=always`：进程异常退出后自动拉起 / Auto-restart after exit
- `RestartSec=3`：避免崩溃重启风暴 / Back off between restarts
- `MemoryMax=400M`（示例）：限制单服务 RSS，降低拖死整机的概率（Zero2W 请按实际调）/ Cap service RSS to reduce OOM risk

示例片段 / Example snippet：

```ini
[Service]
Restart=always
RestartSec=3
# MemoryMax=400M
```

## OOM 观测 / OOM observation

在设备上可快速确认是否被 OOM killer 终止：

```bash
sudo journalctl -k -b | grep -i -E 'oom|killed process|Out of memory'
sudo dmesg -T | grep -i -E 'oom|killed process'
```

## CMA 低余量的判读 / Interpreting low CMA free memory

不能仅凭 `/proc/meminfo` 的 `CmaFree` 很低判定相机泄漏或即将分配失败。
CMA 区域也可供可迁移页使用；立即空闲的页数与 CMA 分配位图中的可用容量不是同一指标。
必须把余量、实际分配结果和采集进度一起看。
/ Low `CmaFree` alone does not establish a camera leak or imminent allocation failure.
Movable pages can occupy the CMA region, so immediately free pages and capacity available
in the CMA allocation bitmap measure different things. Correlate both with allocation
results and capture progress.

| 证据 / Evidence | 判断用途 / Interpretation |
| --- | --- |
| `CmaFree`、`MemAvailable`、RSS + swap、页回收与换页计数 / Memory and reclaim counters | 观察压力与长期趋势；RSS 单独增长也可能只是换入 / Track pressure and trends; RSS growth alone may reflect swap-in |
| CMA `available_pages` 或 `cma_alloc_start.available_count` / CMA bitmap availability | 区分专用连续缓冲占用与普通可迁移页；容量不保证任意大小请求都成功 / Distinguish CMA reservations from movable-page use; capacity does not guarantee every request size |
| `cma_alloc_finish.errorno`、分配耗时、同一 PFN 和页数的释放 / Allocation outcome, latency and matched releases | 确认真实失败、延迟或未释放分配；`busy_retry` 本身不是最终失败 / Identify failures, latency and unreleased allocations; a busy retry is not a final failure |
| 预览及分析帧进度、编码错误、FD/线程、启停后占用 / Progress, encode errors, descriptors, threads and post-stop ownership | 判断压力是否实际影响服务，以及停止后能否恢复 / Establish service impact and recovery after stop |

内核可能未提供 `/sys/kernel/mm/cma` 或 CMA debugfs。此时可在维护窗口使用独立
tracefs instance 记录 `events/cma`，保存跟踪丢失计数；结束后禁用事件、关闭读取句柄并删除
该实例，保持全局跟踪配置不变。有丢失事件时，不能凭分配/释放计数断言无泄漏。
/ If CMA sysfs/debugfs statistics are unavailable, use a dedicated tracefs instance during
maintenance and record its loss counters. Disable its events, close readers and remove
the instance afterward without changing global tracing. Missing events invalidate a
leak-free conclusion based on allocation/release counts.

需要验证低余量下的真实分配时，可在受控测试中从 `default_cma_region` DMA heap
申请一块有限大小的连续缓冲并立即关闭返回的 fd。记录申请前余量、大小、耗时和结果，
为探针设置独立进程超时并限制并发。它只能证明该时刻、该大小的请求，不能替代相机
反复启停和长时负载测试，也不能证明更大分辨率或其他后端的余量。
/ A bounded allocation from the `default_cma_region` DMA heap, immediately released by
closing its fd, can test real allocation under low free memory. Record prior free memory,
size, latency and outcome; bound the probe process and concurrency. This proves only that
request at that moment, not larger resolutions, other backends or long-term stability.

参考 / References: [CMA statistics](https://www.kernel.org/doc/Documentation/ABI/testing/sysfs-kernel-mm-cma),
[CMA and movable pages](https://docs.kernel.org/mm/physical_memory.html),
[CMA allocation implementation](https://github.com/torvalds/linux/blob/master/mm/cma.c),
[trace instances](https://docs.kernel.org/trace/ftrace.html#instances),
[DMA buffer heaps](https://docs.kernel.org/userspace-api/dma-buf-heaps.html).

## 与预览相关的环境变量 / Preview-related environment variables

| 变量 / Variable | 含义 / Meaning |
|-----------------|----------------|
| `OGSCOPE_PREVIEW_JPEG_QUALITY` | 共享预览 JPEG 质量（与调试 MJPEG 默认质量一致）/ Shared preview JPEG quality |
| `OGSCOPE_SHARED_PREVIEW_FPS` | 共享抓帧与 MJPEG 推送目标帧率 / Shared grabber and MJPEG pacing FPS |
| `OGSCOPE_STREAM_MJPEG_CLIENT_STALL_TIMEOUT_MS` | 下游 MJPEG 发送无进展超时，0 表示禁用 / Downstream MJPEG send-stall timeout; 0 disables it |
| `OGSCOPE_DEBUG_PREVIEW_MIN_INTERVAL_MS` | 调试「单帧预览」接口每客户端最小间隔（毫秒）；过短返回 304 / Min interval for `/api/dev/debug/camera/preview` per client |
| `OGSCOPE_CAMERA_CAPTURE_TIMEOUT_SEC` | 单次 Picamera2 抓帧的硬超时，必须高于最长曝光；超时后复用未完成任务，不重复排队新请求 / Hard timeout for one Picamera2 capture; keep above maximum exposure and do not queue duplicate jobs after timeout |
| `OGSCOPE_KEEP_RAW_CACHE` | `1` 时在共享管理器中常驻 `_latest_raw`；默认 `0` 以省内存 / Retain raw frame cache when `1` |

当抓帧线程、`stop` 或 `close` 无法在限时内结束时，CameraManager 会保留原相机句柄并报告
`restart_required=true`，禁止同一进程创建第二个 Picamera2 实例。此状态需要重启 `ogscope.service`
来释放 libcamera 资源。/ When a capture worker, `stop`, or `close` cannot finish within
its deadline, CameraManager retains the original handle, reports `restart_required=true`, and
blocks a second Picamera2 instance in the same process. Restart `ogscope.service` to release the
libcamera resources.
