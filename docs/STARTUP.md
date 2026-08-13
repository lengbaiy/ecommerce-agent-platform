# 电商智能运营 Agent 平台启动指南

本文说明如何在 Windows 本机启动前端和后端，以及如何进行验证、停止和故障排查。

## 1. 运行环境

- Windows 10/11 与 PowerShell 5.1 或更高版本
- Python 3.11 或更高版本
- Node.js 20.19+、22.13+ 或更高稳定版本
- npm 10+
- 可选：Docker Desktop，用于启动完整依赖服务

在 PowerShell 中确认环境：

```powershell
python --version
node --version
npm --version
```

## 2. 首次安装

以下命令均在项目根目录执行。

### 后端

```powershell
python -m venv backend/.venv
./backend/.venv/Scripts/python.exe -m pip install --upgrade pip
./backend/.venv/Scripts/python.exe -m pip install -e "./backend[dev]"
```

### 前端

```powershell
Set-Location frontend
npm install
Set-Location ..
```

如果仓库的 `package-lock.json` 未变化，CI 或全新环境也可以使用 `npm ci` 获得严格一致的依赖版本。

## 3. 一键启动（推荐）

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./scripts/Start-Local.ps1
```

脚本会执行以下操作：

- 使用 `backend/.venv` 启动 FastAPI，默认端口为 `8000`；
- 启动 Vite 开发服务器，默认端口为 `5173`；
- 配置前端 `/api` 代理并等待两个服务通过健康检查；
- 将日志与 PID 文件写入 `work/`。

启动成功后访问：

- Web 管理端：<http://127.0.0.1:5173/>
- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>
- 就绪检查：<http://127.0.0.1:8000/ready>

需要使用其他端口时：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./scripts/Start-Local.ps1 -ApiPort 8010 -WebPort 5180
```

## 4. 停止项目

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./scripts/Stop-Local.ps1
```

该脚本只会停止由启动脚本记录在 `work/api.pid` 和 `work/web.pid` 中的进程。

## 5. 手动启动

需要分别观察前后端终端输出时，可以打开两个 PowerShell 窗口。

窗口一（后端）：

```powershell
Set-Location backend
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

窗口二（前端）：

```powershell
Set-Location frontend
$env:VITE_API_PROXY_TARGET = "http://127.0.0.1:8000"
npm run dev -- --host 127.0.0.1 --port 5173
```

按 `Ctrl+C` 分别停止两个前台进程。

## 6. Docker 启动

安装并启动 Docker Desktop 后，在项目根目录执行：

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Docker Compose 会同时启动 Web、API、PostgreSQL、Redis、Qdrant、MinIO、Worker 和 Scheduler。停止并保留数据卷：

```powershell
docker compose down
```

如需同时删除本项目的 Docker 数据卷，请明确执行 `docker compose down -v`；该操作会删除数据库及其他持久化数据。

## 7. 代码验证

一键运行前后端静态检查、测试和生产构建：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./scripts/Verify-Code.ps1
```

也可以分别运行：

```powershell
./backend/.venv/Scripts/python.exe -m pytest -q backend/tests

Set-Location frontend
npm run lint
npm run format:check
npm run build
```

## 8. 日志与故障排查

本地后台启动日志位于：

- `work/api.log`、`work/api.error.log`
- `work/web.log`、`work/web.error.log`

常见问题：

1. **提示虚拟环境不存在**：重新执行“首次安装”的后端命令。
2. **提示 `node_modules` 不存在**：进入 `frontend` 执行 `npm install`。
3. **端口被占用**：先关闭占用进程，或通过 `-ApiPort`、`-WebPort` 指定新端口。
4. **PowerShell 禁止执行脚本**：可在当前窗口执行 `Set-ExecutionPolicy -Scope Process Bypass`，然后重试。
5. **Node.js 引擎警告**：升级到 Node.js 22.13+，再删除 `frontend/node_modules` 并重新安装依赖。

本地版本使用演示数据完成业务闭环，不会自动连接真实电商账户或生产数据。

## 9. 身份认证与数据库迁移

本地默认使用内置账号登录和 JWT 会话。首次启动账号为租户 `local`、用户名 `admin`、密码 `Admin@123456`；登录前必须完成一次性滑块验证。请在共享开发环境立即修改 `BOOTSTRAP_ADMIN_PASSWORD`。

生产配置至少需要：

```powershell
$env:APP_ENV = "production"
$env:AUTH_MODE = "jwt"
$env:JWT_SECRET = "从密钥管理服务注入的至少 32 字符密钥"
$env:JWT_ISSUER = "https://identity.example.com/"
$env:JWT_AUDIENCE = "ecommerce-agent-api"
$env:AUTO_CREATE_SCHEMA = "false"
```

生产启动前执行迁移：

```powershell
Set-Location backend
./.venv/Scripts/python.exe -m alembic upgrade head
```

如需将任务交给独立 Worker，将 API 与 Worker 同时设置为 `TASK_EXECUTION_MODE=worker`，再运行：

```powershell
Set-Location backend
./.venv/Scripts/python.exe -m app.worker
```

## 10. 移动运营端

移动运营端当前是独立的 Vue 3 + Vite 响应式 H5 框架：

```powershell
Set-Location clients/mobile-ops
npm install
npm run dev
```

微信小程序适配应作为独立客户端工程接入，不与 Web/H5 的稳定依赖树混装。
