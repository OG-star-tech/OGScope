# OGScope System Architecture (Bilingual)

> 本文档给出 OGScope 的“系统级”架构视图（区别于 API 路由分层），强调核心边界、用户层与开发者工具层隔离、以及运维层的横切属性。  
> This document provides the system-level architecture view of OGScope (different from API route layering), emphasizing core boundary, separation between user and developer surfaces, and the cross-cutting nature of operations.

## Architecture Diagram / 架构图

```mermaid
flowchart TD
  externalCaller["外部调用方 / External Caller<br/>external integrator or Other Clients"]

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
    hwAdapter["硬件适配 / Hardware Adapters"]
    sysAdapter["系统适配 / System Adapters"]
    dataAdapter["数据读写适配 / Data IO Adapters"]
  end

  subgraph dataAlgoLayer["数据与算法资源层 / Data and Algorithm Resource Layer"]
    solveDb["解算数据库 / Plate Solve Database"]
    algoEngine["解算算法引擎 / Solve Algorithm Engine"]
    calibrationData["校准与历史数据 / Calibration and History Data"]
  end

  subgraph peripheralLayer["外围硬件层 / Peripheral Hardware Layer"]
    cameraHw["相机 / Camera IMX327"]
    wifiHw["网络模块 / WiFi and NetworkManager"]
    gpioHw["应急GPIO / Emergency GPIO"]
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

  corePolicy --> hwAdapter
  corePolicy --> sysAdapter
  corePolicy --> dataAdapter

  dataAdapter --> solveDb
  dataAdapter --> calibrationData
  domainLayer --> algoEngine
  algoEngine --> solveDb

  hwAdapter --> cameraHw
  hwAdapter --> wifiHw
  hwAdapter --> gpioHw
  hwAdapter -.-> magnetometerHw
  hwAdapter -.-> gpsHw
  hwAdapter -.-> gyroHw
  hwAdapter -.-> accelHw
  hwAdapter -.-> displayHw

  serviceManager --> webGateway
  envBootstrap --> serviceManager
  deployScripts --> envBootstrap
  deployScripts --> serviceManager
  serviceManager --> observability
  observability --> webGateway
  observability --> appLayer
  observability --> hwAdapter

  boundaryNote["架构硬约束 / Hard Rule<br/>核心层不对外暴露，不允许被外部直接调用<br/>Core layer is not public and cannot be invoked directly by external callers"]
  boundaryNote -.-> coreBoundary
```



## Key Clarifications / 关键说明

- **FastAPI is not core / FastAPI 不是核心层**  
`webGateway` 属于接口网关层，核心业务位于 `appLayer/domainLayer/corePolicy`。
- **Core cannot be called directly / 核心层禁止外部直调**  
外部调用方（含 external integrator）必须经 `REST Contract Entry`，不能直接调用核心模块。
- **Developer tooling is not user surface / 开发者工具层不等于用户层**  
`userSurface` 与 `devSurface` 分层，路径、权限和稳定性承诺都应分离。
- **Solve data is not peripheral hardware / 解算数据不属于外围硬件**  
`Plate Solve Database` 被归入“数据与算法资源层”，与实体硬件层解耦。
- **Runtime/Ops is cross-cutting / 运维层是横切层**  
运维能力同时作用于网关层、核心层和基础设施层，不是单一依赖于接口层。

