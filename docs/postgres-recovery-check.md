# PostgreSQL 迁移与任务恢复检查

`migrations/versions/0001_server_foundation.py` 仍是 PostgreSQL 的权威表结构来源；离线 SQL 检查不连接生产库。运行：

```powershell
E:\Banboos2.0\.venv\Scripts\python.exe scripts\verify_persistence_recovery.py `
  --report E:\Banboos2.0\var\migrations\persistence-recovery-report.json
```

检查包含两部分：Alembic `upgrade head --sql` 能生成迁移脚本；任务写入本地持久化队列后模拟 Worker 中断，重启恢复会把 `running` 任务原子地重新排为 `queued`，随后任务可完成且状态在重新打开 SQLite 后仍为 `succeeded`。本地 SQLite 只是开发/断网缓存，生产仍需 PostgreSQL + Redis，并在预发布环境执行真实备份、恢复和多 Worker 演练。
