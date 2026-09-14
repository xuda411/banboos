# Banboos 2.0 初始架构

## 目标

以同一套领域规则支持 PyQt6 专业桌面端、React Web 端和未来电站运营端。客户端不直接连接生产数据库，现场设备不直接暴露到公网。

## 依赖方向

```text
Client → API / Application → Domain
                         ↘ Infrastructure
Edge → Ingest → Time-series / Raw storage
```

第一阶段采用模块化单体：FastAPI、worker、数据库和对象存储可以独立进程部署，但领域代码保持一个版本库。经过吞吐和团队边界验证后，才拆分服务。

## 数据分层

1. Raw：原始电价、气象、遥测、设备报文和导入文件，只追加不覆盖。
2. Quality：质量规则版本、问题、去重代表、冲突候选和人工复核。
3. Canonical：统一点位、单位、时区、质量码和来源后的事实数据。
4. Aggregate：分钟、小时、日、月、年统计和运营指标。
5. Result：LP、财务、预测、调度计划和报告，绑定输入快照和算法版本。

## 首轮 ADR

- `ADR/0001-modular-monolith.md`：先模块化单体，再按瓶颈拆服务。
- `ADR/0002-edge-first-control.md`：现场联锁和断网自治优先于云端控制。
- `ADR/0003-legacy-replay-only.md`：1.6.6 只读隔离迁移和回放。
