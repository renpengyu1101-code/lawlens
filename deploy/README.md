# 部署说明

当前状态：**本地单机**。`start.cmd` 起一个 uvicorn 进程，监听 `0.0.0.0:8000`，前端静态文件由后端托管，数据存 SQLite + 本地目录。

- 数据目录：`diligence-platform/backend/data/`（`app.db` + `uploads/` + `reports/`），当前约 17 MB
- 配置：`diligence-platform/.env`（密钥、模型、管理员）
- 关掉那个命令行窗口 = 服务停止

下面三条路，按"打算给谁用"选。

---

## 一、内网试用（最省事，推荐先走这条）

目标：几位同事在内网访问 `http://<内网IP>:8000`。

### Windows 内网一台常开机器

1. 装 Python 3.12 与 Node 20（Node 只用于构建前端，之后不需要）
2. 拷贝整个 `diligence-platform` 目录
3. 首次：
   ```powershell
   python -m venv .venv
   .venv\Scripts\pip install -r backend\requirements.txt
   cd frontend && pnpm install && pnpm build && cd ..
   start.cmd -Init          # 生成 .env，填 DEEPSEEK_API_KEY
   ```
4. 让它开机自启、不依赖登录窗口——用**任务计划程序**：
   - 触发器：开机时
   - 操作：`cmd.exe /c "D:\path\diligence-platform\start.cmd"`
   - 勾选「不管用户是否登录都要运行」「使用最高权限」
5. 防火墙放行 8000：
   ```powershell
   New-NetFirewallRule -DisplayName "LawLens 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
   ```

### Linux 内网服务器

用 `lawlens.service`（见同目录），放到 `/etc/systemd/system/`，`systemctl enable --now lawlens`。前面不用挂 nginx，直接 8000 即可。

---

## 二、容器化（换机器最省心）

同目录有 `Dockerfile` + `docker-compose.yml`，镜像里包含前端构建产物。

```bash
cd deploy
cp ../.env .env            # 密钥、管理员密码在这里
docker compose up -d --build
```

数据落在 `deploy/data/`（compose 挂载），删容器不丢数据。

> 注意：**这台机器没装 Docker，我没法在这里构建验证**。首次部署请先 `docker compose build` 看是否通过；OCR 依赖 `rapidocr-onnxruntime` 会拉 onnxruntime，镜像约 1 GB。

---

## 三、公网发布（给外部客户）

技术上就是"一台云服务器 + 域名 + 证书"，但合规上卡两道：

| 项 | 状态 | 说明 |
|---|---|---|
| **备案** | 未办 | 大陆服务器 + 域名必须备案，通常 2–4 周；个人备案可办，但"法律服务/咨询"类目可能被要求补充资质 |
| **免备案** | 可选 | 香港/新加坡节点可直接上线，但访问慢；客户材料出境涉及数据合规，律师尽调材料尤需谨慎 |
| **HTTPS** | 已支持 | 设 `DILIGENCE_COOKIE_SECURE=1`，会话 cookie 只走加密通道（实测生效） |
| **自助注册** | 已支持关闭 | 设 `DILIGENCE_ALLOW_REGISTER=0`，注册接口直接 403，健康检查会告诉前端隐藏入口（实测生效） |
| **反向代理** | 有配置 | `nginx.conf`：HTTPS、上传上限、长任务超时、安全头 |
| **多租户** | 未做 | 现在是单库单租户；多个客户共用一台会串数据，必须先加 `tenant_id` |
| **备份** | 有脚本 | `backup.ps1`（Windows）；Linux 用 sqlite3 `.backup` + tar，需自己排 cron |
| **日志监控** | 未做 | 只有 uvicorn 标准输出，公网至少要落盘 + 磁盘告警 |
| **数据合规** | 需法务确认 | 正文会发给 DeepSeek；需在合同、页面、隐私政策里写明 |

上线顺序建议：买服务器 → 域名解析 → 备案（等待期可先用内网/临时域名联调）→ 装 Docker → `docker compose up -d` → nginx + certbot → 改管理员密码 → 关注册 → 备份排期。

**这套我只能把配置和脚本准备好，实际部署需要你提供一台能 SSH 的服务器和一个域名。**

---

## 上线前自检

```powershell
# 1. 配置检查（启动日志里以 ! 开头的行必须清零）
start.cmd

# 2. 功能自检（不花钱，本地解析 + 缺料判断）
.venv\Scripts\python.exe scripts\preflight.py "samples\脱敏样例-澄海精工-2026-10\*.pdf"

# 3. 一轮完整核查，确认报告能生成
#    页面里上传上面那个目录 → 开始核查 → 下载 docx
```

## 备份

`backup.ps1` 会做三件事：SQLite 在线备份（`.backup`，不是直接拷文件）、打包 uploads/reports、保留最近 N 份。

```powershell
.\deploy\backup.ps1 -DataDir "D:\lawlens\backend\data" -OutDir "E:\backup\lawlens" -Keep 14
```

放到任务计划程序每天凌晨跑一次即可。
