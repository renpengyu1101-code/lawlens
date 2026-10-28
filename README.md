# LawLens（演示版 v0.1）

把办案经验固化为「材料核查 → 风险识别 → 整改跟踪 → 成果整理」的流水线。
第一个板块：**资产权属与经营基础**。

> **当前为演示版本**：样本为虚构、规则库的规范依据仍在核实（界面标"待补"）。
> 不得用于任何真实交易、尽调或对外法律结论。

---

## 1. 目录结构

```
diligence-platform/
├─ backend/                 FastAPI 后端
│  ├─ app/main.py           路由：认证/项目/上传/流水线/报告/后台
│  ├─ app/agents.py         四个 Agent：意图识别·资料·分析·质检
│  ├─ app/parsers.py        PDF/DOCX/TXT 解析（保留页码锚点）
│  ├─ app/report.py         docx 报告生成
│  ├─ app/rules/*.json      三个板块的核查要点库（办案经验；规范依据待补）
│  └─ data/                 SQLite 与上传文件（运行后生成）
├─ frontend/                React + Vite
├─ samples/虚构测试样本/     7 份虚构材料 + 说明
└─ scripts/                 make_samples.py · smoke_test.py
```

## 2. 快速开始

```powershell
# 1) 后端
cd diligence-platform
python -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt
.venv\Scripts\python scripts\make_samples.py        # 生成虚构样本

# 2) 前端
cd frontend
pnpm install
pnpm run build            # 产物 dist/，后端会自动托管

# 3) 启动（在 backend 目录）
cd ..\backend
..\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 <http://127.0.0.1:8000> 即为完整站点（前端与 API 同源）。

**开发模式**（前端热更新）：`frontend` 目录下 `pnpm run dev`，Vite 会把 `/api` 代理到 8000。

## 3. 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 空 | 为空时进入**演示模式**（规则启发式，界面标注），配置后走模型 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容端点 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 模型名 |
| `DILIGENCE_SECRET` | `dev-only-change-me` | 会话签名密钥，**部署前必须改**（`start.cmd -Init` 会自动生成） |
| `DILIGENCE_DATA_DIR` | `backend/data` | 数据库与文件存储位置 |
| `DILIGENCE_CREDITS_PER_RUN` | `10` | 单次核查消耗积分 |
| `DILIGENCE_REGISTER_BONUS` | `100` | 注册赠送积分 |
| `DILIGENCE_ADMIN_EMAIL` | `admin` | 首个管理员账号（仅首次初始化时生效） |
| `DILIGENCE_ADMIN_PASSWORD` | 空 | 首个管理员密码；留空时首次启动随机生成并打印一次，**已存在的账号不受此变量影响** |
| `DILIGENCE_OCR` | `1` | 设为 `0` 关闭 OCR（扫描件直接标记 `needs_ocr`） |
| `DILIGENCE_OCR_DPI` | `200` | PDF 转图片的分辨率；扫描件模糊时可提到 300 |
| `DILIGENCE_OCR_MAX_PAGES` | `30` | 单份 PDF 最多 OCR 多少页，超过的页不再识别 |
| `DILIGENCE_OCR_MIN_SCORE` | `0.5` | 识别置信度低于此值的行丢弃 |

## 3.2 扫描件与 OCR

支持 PDF / DOCX / TXT / MD / CSV，以及 PNG、JPG、BMP、TIF、WebP 图片。

- PDF 先抽文字层；抽不到（或少于 40 字）才转图片走 OCR——文字版 PDF 不会白跑 OCR。
- OCR 用本地引擎 `rapidocr-onnxruntime`，**不联网、不外发**；识别结果照样带 `[[PAGE n]]` 页码标记，锚点仍然可用。
- 文档状态会显示「OCR 识别」；OCR 也拿不到字才标「扫描件未识别」。
- 依赖已写进 `backend/requirements.txt`；首次 OCR 会加载模型，约 1–2 秒/页（CPU）。

上传前建议先跑预检，它只在本机解析、不调用模型：

```powershell
.venv\Scripts\python.exe scripts\preflight.py "D:\材料\*.pdf"
```

生成一份扫描件样例（把 docx 光栅化成无文字层的 PDF）用于自测：

```powershell
.venv\Scripts\python.exe scripts\make_scan_sample.py
```

## 3.1 内网试用（推荐）

```powershell
# 1) 生成 .env（随机 SECRET，不生成管理员密码）
start.cmd -Init

# 2) 把 DEEPSEEK_API_KEY 填进 .env
# 3) 已有数据库的话，重设管理员密码（对已存在账号，.env 里的 ADMIN_PASSWORD 不生效）
.venv\Scripts\python.exe scripts\set_admin.py admin '你的新密码'

# 4) 启动，绑定 0.0.0.0 并打印内网地址
start.cmd
```

启动日志里以 `!` 开头的三行是安全自检，出现任何一行都要处理：

| 提示 | 含义 |
|---|---|
| `DILIGENCE_SECRET 仍是默认值` | 会话可被伪造，删掉 `.env` 重跑 `-Init` |
| `管理员 … 仍在使用默认密码 123456` | 任何人都能进后台，跑 `scripts/set_admin.py` |
| `启动恢复：N 个项目停在「执行中」` | 上次进程被杀，已标记失败并退还积分 |

首次在内网访问前，Windows 防火墙需要放行端口（管理员 PowerShell）：

```powershell
New-NetFirewallRule -DisplayName "LawLens 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
```

## 4. 管理员账号

- 全新数据库首次启动时：若 `.env` 未设 `DILIGENCE_ADMIN_PASSWORD`，会**随机生成**并打印一次（`!` 开头），登录后请立即修改。
- 已有数据库：用 `scripts/set_admin.py` 重设，`.env` 里的密码不会覆盖已存在账号。
- 普通用户自行注册，注册即得 `DILIGENCE_REGISTER_BONUS` 积分（默认 100）。

## 5. 一次核查的完整链路

```
登录 → 建项目（填主体全称）→ 上传材料 → 发起核查（-10 积分）
   → A 意图识别：自然语言 → 任务单（核查项 + 所需材料）
   → 缺料检查：缺什么直接返回，不消耗模型调用
   → B 资料抽取：字段 + 页码 + 原文片段，同字段多值记为冲突
   → C 分析：按核查要点判定风险等级、给出整改建议
   → D 质检：逐条回原文校验证据是否能定位；不能定位的判为不合格
   → 报告：docx，每条结论附《文件》第 N 页「原文」
```

## 5.1 核查范围：固定三个维度

每次核查都覆盖下面三个维度，**不提供"选一个知识库"的选项**：先跑资产，再跑劳动，最后跑股权退出，单个维度材料不全只跳过该维度，三个都缺才转「待补材料」。

| 维度 | 核查要点 | 样本目录 |
|---|---|---|
| 资产权属与经营基础 | AST-01 权属主体、AST-02 权证完整、AST-03 权利负担、AST-04 租赁合法、AST-05 资质有效、AST-06 知识产权 | `samples/虚构测试样本/` |
| 劳动用工合规 | LAB-01 合同签订、LAB-02 社保、LAB-03 派遣、LAB-04 工时、LAB-05 竞业、LAB-06 争议 | `samples/虚构测试样本-劳动用工/` |
| 投资退出与股权回购 | EQT-01 出资、EQT-02 代持、EQT-03 对赌回购、EQT-04 优先权、EQT-05 变动程序、EQT-06 特殊权利 | `samples/虚构测试样本-投资退出/` |

进度在点「开始核查」后就地显示：三个维度标签 + 当前步骤 + 步骤日志，数据来自 `GET /api/projects/{id}/progress`。

## 5.2 设置（/app/settings）

- **配色**：藏青 / 墨 / 苔，只影响本机显示，存 `localStorage`。
- **修改密码**：校验原密码后更新，操作写入审计日志。
- **模型接入**：API Key、模型名、接口地址。**密钥只存在本浏览器**，发起核查时通过请求头 `X-LLM-Key` 传给后端，不写入数据库、不落日志；可点"测试连接"验证。

## 6. 已验证

**后端端到端**（`python scripts/smoke_test.py`，47 项全过）
- 注册/登录、积分赠送与扣减、失败退还
- 未登录 401、普通用户访问后台 403、积分不足 402 且不改变项目状态
- 7 份材料上传与解析
- 四个 Agent 串联，识别出 6 条风险：权属主体不一致、抵押、质押、租赁出租方非产权人、资质过期、材料冲突
- 每条结论均带证据锚点，质检全部通过
- docx 报告生成与下载（约 40KB）
- 复核闸门：命中条件后进入待律师复核，管理员复核通过才转「已出报告」
- 量化评分：单项目五维评分 + 主体总表（三板块聚合，缺板块记 N/A）
- 管理后台：概览、用户积分、规则库、审计日志

> 冒烟测试会清空其数据目录。演示库正在运行时，用独立目录跑：
> `$env:DILIGENCE_DATA_DIR="...\backend\data-smoke"` 后再执行，避免清掉正在演示的数据。

**真实 HTTP 链路**（运行中的服务，curl）
- 注册 → 建项目 → 7 次上传 → 发起任务 → 6 条结论 → 报告 40KB → 静态资源 200

**浏览器 UI**（`node scripts/ui_check.mjs`，Chrome headless，37 项全过，自动造数据）
- 首页：LawLens、一句话、内嵌登录表单；不含旧名、板块与流程
- 在首页表单直接输入账号密码登录 → 直接进入工作台（不经过登录页）
- 在对话框写一句话点"开始核查" → 直接创建项目并进入项目页
- 八枚透镜在全视口范围内游走并相互碰撞反弹（活动范围为整个网页，不限于文字场）；镜内放大 1.12–1.24 倍；底部风险文字 24 条
- 已登录时首页显示"进入工作台"与"退出登录"，未登录时显示内嵌登录表单
- 工作台：5 步工作流预览、对话框（问题/知识库/主体/附件）、最近项目列表
- 项目详情 6 条结论、7 条证据引用、质检结论、上传控件不裸露
- 管理后台四个标签页与要点库"待补"标注
- 截图见 `ui-shots/`


> 说明：以上验证的是"系统能按要求工作"，不代表核查结论在法律上正确——后者需律师判断。


## 7. 已知限制（刻意保留，不隐藏）

1. **规则库无规范依据**：核查要点来自办案经验，`rule_ref` 为空即显示"待补"，不得据以作出法律结论。
2. **样本为虚构**：仅验证系统机制，不代表真实企业情况。
3. **演示模式为规则启发式**：未接模型时，抽取靠正则，能力有限；配置 `DEEPSEEK_API_KEY` 后切换为模型抽取。
4. **未做**：支付、实名认证、多租户隔离、OCR、高并发与灾备。
5. **质检的边界**：能校验"证据原文是否存在"，不能校验"法律判断是否正确"——后者仍是律师的工作。
