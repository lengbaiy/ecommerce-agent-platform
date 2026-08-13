# 数据库迁移

数据库结构使用 Alembic 管理。生产环境禁止通过应用启动自动建表：

```powershell
$env:AUTO_CREATE_SCHEMA = "false"
./.venv/Scripts/python.exe -m alembic upgrade head
```

开发环境默认启用 `AUTO_CREATE_SCHEMA=true`，用于首次启动 SQLite 演示数据库。任何正式环境都应先执行迁移，再启动 API 和 Worker。
