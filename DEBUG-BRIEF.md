# 调试交接说明（给另一个 AI / 开发者）

> 读这一份就能接手。所有路径为本机绝对路径，换机器需整体替换。

## 0. 一句话背景

LawLens：港股 IPO 法律尽调辅助平台（演示版）。用户上传材料 → 四段流水线（意图识别 / 资料抽取 / 风险分析 / 质检）→ 每条结论必须带「文件 + 页码 + 原文」证据锚点 → 出 docx 报告。当前是**演示模式（规则引擎）**，未接模型。

## 1. 目录

```
D:\Users\92182\Documents\deepseek-harness\default-workspace\
├─ diligence-platform\        网站本体
│  ├─ backend\app\            FastAPI 后端（入口 main.py）
│  ├─ backend\data\           SQLite + 上传文件（运行后生成，勿删）
│  ├─ frontend\src\           React 源码（Vite）
│  ├─ frontend\dist\          构建产物，后端直接托管；改完前端必须重新 build
│  ├─ scripts\                造样本 / 冒烟 / UI 校验
│  ├─ samples\                虚构样本（含澜川精密案件）
│  └─ .venv\                  Python 依赖
└─ analysis-library\          招股书与失败案例分析库（独立于网站）
```

## 2. 运行环境

- Windows + PowerShell（本机是 5.1，不支持 `Invoke-RestMethod -Form`，用 `curl.exe`）
- Python：`D:\Users\92182\Documents\deepseek-harness\default-workspace\diligence-platform\.venv\Scripts\python.exe`
- Node：`C:\Users\92182\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe`
- pnpm：`C:\Users\92182\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\pnpm\bin\pnpm.mjs`（用 `node <path> run build` 调用）

## 3. 命令

```powershell
# 启动后端（在 backend 目录）
..\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 前端构建（在 frontend 目录）
& $node $pnpm run build

# 后端端到端（42 项断言；用独立数据目录，避免清空演示库）
$env:DILIGENCE_DATA_DIR="...\backend\data-smoke"
..\.venv\Scripts\python ..\scripts\smoke_test.py

# 浏览器校验 + 截图（35 项；自动造数据）
& $node scripts\ui_check.mjs "C:\Program Files\Google\Chrome\Application\chrome.exe" ui-shots
```

- 服务：http://127.0.0.1:8000 ，管理员 `admin / 123456`
- 不配模型也能全流程跑；配了 DeepSeek Key 只有「资料抽取」走模型。

## 4. 架构要点

- **数据模型**：`projects → documents → document_groups → document_versions → paragraphs`；结论在 `findings` + `citations`。
- **版本**：段落有跨版本稳定 `uid`（difflib 对齐，阈值 0.7）；上传新版本会更新对应 `documents` 行，保证流水线读当前版。
- **板块**：asset / labor / equity，各有规则库 `backend/app/rules/*.json` 与独立判读函数。
- **证据**：`citations` 存 document_id + page + quote；质检用字符串回查原文，定位不到即判 fail。
- **报告**：`report.py` 生成 docx，未通过质检的结论会显著标注。

## 5. 当前状态（别重复验证）

- 能跑：三板块流水线、版本上传与对比、积分、后台、设置（配色/改密/API 配置）。
- 已验证：后端 42 项、浏览器 35 项，全过。
- **未验证**：模型模式（无真实 Key，代码路径写好了但没跑通）。
- **已知缺陷**：
  1. 质检失败后的「回退重跑」是空转——分析是确定性规则，重跑结果相同。
  2. 规则库 `rule_ref` 全为空，界面标「待补」，不能作为法律结论依据。
  3. 上传新版本后，材料列表显示的是新文件名（非固定组名）。
  4. SQLite 未设 busy_timeout，后台任务与请求并发写有锁风险。
  5. 首页透镜是 CSS「复制放大 + 圆形裁切」，镜边会切断文字；要真畸变需 WebGL。

## 6. 已知坑（踩过的，别再踩）

1. **pypdf 解中文 PDF 会乱码**（CFF 字体），必须用 PyMuPDF（fitz）。
2. **PowerShell 单引号字符串里的 `` `n `` 不会换行**，会把字面量写进文件——批改代码优先用编辑工具，不要用 `-replace` 拼多行。
3. 前端改完**不 build**，浏览器看到的还是旧包（index.html 已设 no-cache，但构建瞬间刷新可能 404）。
4. 无头 Chrome 默认 `prefers-reduced-motion: reduce`；首页动效已强制开，但复制动画逻辑时要留意。
5. `scripts/smoke_test.py` 会删自己的数据目录；**不要**把 `DILIGENCE_DATA_DIR` 指向正在服务的 `backend/data`。
6. TestClient 与真实服务不要共用同一个库文件。
7. 版本上传会改写 `documents` 行（文件名/路径/正文），历史版本仍留在 `document_versions` + `paragraphs`。

## 7. 改代码前必须知道的约束

- 项目根 `AGENTS.md` 有三条硬原则：**不编造数据、引用必须回原文核对、未验证不得交付**。
- 任何结论必须带证据锚点；不要为了「看起来完整」补字段或编页码。
- 改动 `db.py` 的表结构要考虑已有数据：`init_db` 只 `CREATE TABLE IF NOT EXISTS`，不会迁移列；加列要写迁移函数。
- 改完必须跑上面两条测试；UI 测试会截图，可肉眼复核。

## 8. 验收标准

1. `smoke_test.py` 全过（当前 42 项）；
2. `ui_check.mjs` 全过（当前 35 项）；
3. 首页能登录、工作台能建项目、项目页能出结论与报告；
4. 不新增无出处的数据。
