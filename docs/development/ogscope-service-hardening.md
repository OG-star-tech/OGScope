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

## 与预览相关的环境变量 / Preview-related environment variables

| 变量 / Variable | 含义 / Meaning |
|-----------------|----------------|
| `OGSCOPE_PREVIEW_JPEG_QUALITY` | 共享预览 JPEG 质量（与调试 MJPEG 默认质量一致）/ Shared preview JPEG quality |
| `OGSCOPE_SHARED_PREVIEW_FPS` | 共享抓帧与 MJPEG 推送目标帧率 / Shared grabber and MJPEG pacing FPS |
| `OGSCOPE_DEBUG_PREVIEW_MIN_INTERVAL_MS` | 调试「单帧预览」接口每客户端最小间隔（毫秒）；过短返回 304 / Min interval for `/api/debug/camera/preview` per client |
| `OGSCOPE_KEEP_RAW_CACHE` | `1` 时在共享管理器中常驻 `_latest_raw`；默认 `0` 以省内存 / Retain raw frame cache when `1` |
