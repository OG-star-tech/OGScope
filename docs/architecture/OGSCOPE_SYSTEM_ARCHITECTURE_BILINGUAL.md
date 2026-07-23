# OGScope System Architecture (Bilingual)

> 本文档给出 OGScope 的“系统级”架构视图（区别于 API 路由分层），强调核心边界、用户层与开发者工具层隔离、运维层横切属性，以及 hardware plane 与 subordinate 集成边界。  
> This document provides OGScope system-level architecture (different from API route layering), emphasizing core boundary, user/developer surface separation, cross-cutting operations, and hardware-plane / subordinate integration boundaries.

## Architecture Diagram / 架构图

```mermaid
flowchart TD
  externalCaller["外部调用方 / External Caller<br/>Integrators and Clients"]

  subgraph interfaceLayer["接口与契约层 / Interface and Contract Layer"]
    restContract["REST契约入口 / REST Contract Entry<br/>/api/core/v1/*"]
    devContract["开发者入口 / Developer Contract Entry<br/>/api/dev/*"]
    openApiDocs["接口文档层 / API Docs Layer<br/>/docs /docs/dev /docs/all"]
    webGateway["Web网关 / FastAPI Gateway"]
  end

  subgraph surfaceLayer["交互表面层 / Surface Layer"]
    userSurface["用户层 / User Surface<br/>Home and Stable Operations"]
    devSurface["开发者工具层 / Developer Tooling Surface<br/>Debug and Diagnostics"]
  end

  subgraph coreBoundary["核心边界内层（不对外） / Core Internal Boundary (Not Public)"]
    appLayer["应用编排层 / Application Orchestration Layer"]
    domainLayer["领域服务层 / Domain Service Layer<br/>camera analysis network system shared"]
    corePolicy["核心策略与状态机 / Core Policies and State Machines"]
  end

  subgraph infraLayer["基础设施与适配层 / Infrastructure and Adapter Layer"]
    hwClient["硬件平面客户端 / Hardware Plane Client"]
    sysAdapter["系统适配 / System Adapters"]
    dataAdapter["数据读写适配 / Data IO Adapters"]
  end

  subgraph sharedHardwarePlane["硬件平面（进程内） / Hardware Plane (In-Process)"]
    capabilityRegistry["能力注册中心 / Capability Registry"]
    controlPlane["控制面 / Control Plane<br/>In-process + optional UDS JSON-RPC"]
    dataPlane["数据面 / Data Plane<br/>Ring Buffer + UDS Notify"]
    eventPlane["事件面 / Event Plane<br/>D-Bus Signals Optional"]
    profileConfig["环境配置档 / Environment Profiles<br/>standalone or subordinate"]
  end

  subgraph externalSensor["外部传感器服务（subordinate） / External Sensor Provider"]
    udsSensor["UDS JSON-RPC<br/>hardware-plane-uds-v1"]
  end

  subgraph dataAlgoLayer["数据与算法资源层 / Data and Algorithm Resource Layer"]
    solveDb["解算数据库 / Plate Solve Database"]
    algoEngine["解算算法引擎 / Solve Algorithm Engine"]
    calibrationData["校准与历史数据 / Calibration and History Data"]
  end

  subgraph peripheralLayer["外围硬件层 / Peripheral Hardware Layer"]
    cameraHw["相机 / Camera IMX327"]
    wifiHw["网络模块 / WiFi and NetworkManager"]
    magnetometerHw["磁力计（规划） / Magnetometer (Planned)"]
    gpsHw["GPS（规划） / GPS (Planned)"]
    gyroHw["陀螺仪（规划） / Gyroscope (Planned)"]
    accelHw["加速度计（规划） / Accelerometer (Planned)"]
    displayHw["屏幕集成（规划） / Display Integration (Planned)"]
  end

  subgraph runtimeOpsLayer["运行与运维横切层 / Cross-Cutting Runtime and Operations Layer"]
    envBootstrap["环境初始化 / Environment Bootstrap<br/>install and dependency bootstrap"]
    deployScripts["部署脚本 / Deployment Scripts<br/>install update sync uninstall"]
    serviceManager["服务托管 / Service Manager<br/>systemd and startup policy"]
    observability["可观测性 / Observability<br/>logging health metrics"]
  end

  externalCaller --> restContract
  userSurface --> webGateway
  devSurface --> webGateway
  webGateway --> restContract
  webGateway --> devContract
  webGateway --> openApiDocs

  restContract --> appLayer
  devContract --> appLayer
  appLayer --> domainLayer
  domainLayer --> corePolicy

  corePolicy --> hwClient
  corePolicy --> sysAdapter
  corePolicy --> dataAdapter

  dataAdapter --> solveDb
  dataAdapter --> calibrationData
  domainLayer --> algoEngine
  algoEngine --> solveDb

  profileConfig --> capabilityRegistry
  capabilityRegistry --> controlPlane
  hwClient --> controlPlane
  hwClient --> dataPlane
  hwClient --> eventPlane
  hwClient -.->|"subordinate"| udsSensor

  controlPlane --> cameraHw
  controlPlane --> wifiHw
  controlPlane --> gpioHw
  controlPlane -.-> magnetometerHw
  controlPlane -.-> gpsHw
  controlPlane -.-> gyroHw
  controlPlane -.-> accelHw
  controlPlane -.-> displayHw

  serviceManager --> webGateway
  envBootstrap --> serviceManager
  deployScripts --> envBootstrap
  deployScripts --> serviceManager
  serviceManager --> observability
  observability --> webGateway
  observability --> appLayer
  observability --> hwClient

  boundaryNote["架构硬约束 / Hard Rule<br/>核心层不对外暴露，不允许被外部直接调用<br/>Core layer is not public and cannot be invoked directly by external callers"]
  boundaryNote -.-> coreBoundary
```



## Key Clarifications / 关键说明

- **FastAPI is not core / FastAPI 不是核心层**  
`webGateway` 属于接口网关层，核心业务位于 `appLayer/domainLayer/corePolicy`。
- **Core cannot be called directly / 核心层禁止外部直调**  
外部调用方必须经 `REST Contract Entry`（`/api/core/v1/*`），不能直接调用核心模块。
- **Developer tooling is not user surface / 开发者工具层不等于用户层**  
`userSurface` 与 `devSurface` 分层，路径、权限和稳定性承诺都应分离。
- **Solve data is not peripheral hardware / 解算数据不属于外围硬件**  
`Plate Solve Database` 被归入“数据与算法资源层”，与实体硬件层解耦。
- **Runtime/Ops is cross-cutting / 运维层是横切层**  
运维能力同时作用于网关层、核心层和基础设施层，不是单一依赖于接口层。
- **Hardware plane profiles / 硬件平面配置档**  
通过 `OGSCOPE_HARDWARE_PLANE_ROLE` 在 `standalone` 与 `subordinate` 间切换；详见 [subordinate-mode](../contracts/subordinate-mode.md)。
- **Registerable capabilities / 能力可注册**  
传感器与人机交互硬件通过 `Capability Registry` 管理，支持不同环境装配不同驱动逻辑。
- **Unified hardware contract / 统一硬件契约**  
OGScope 通过 `Hardware Plane Client` 使用统一能力接口（status/read/command/subscribe）。
- **Subordinate integration boundary / subordinate 集成边界**  
在 `subordinate` 角色下，上层集成方业务协作走 `REST /api/core/v1/*`；传感器读请求通过本机 `UDS JSON-RPC` 委托给外部提供方（[hardware-plane-uds-v1](../contracts/hardware-plane-uds-v1.md)）。本地传感器/HMI 默认禁用，相机仍由 OGScope 维护。
