# 来源登记表 · LexDesk 参考笔记

交付物：`design-notes/DESIGN-reference-lexdesk.md`
制作人：助手 ｜ 制作日期：2026-10-28 ｜ 核对人：助手（非独立复校）

| # | 数据/结论（原样摘录） | 来源名称与发布方 | 定位 | 版本或日期 | 链接或文号 | 取得方式 | 核对人 | 核对日期 | 状态 | 备注 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `<title>LexDesk · 法律人的 AI 工作台</title>`；入口 `assets/index-BU20CUYI.js`、`assets/index-D8rLeU-F.css` | ai-lawworkbench.tech | `_evidence/index.html` 第 5、7、8 行 | 2026-10-28 抓取 | https://www.ai-lawworkbench.tech/ | 原件（站点静态文件） | 助手 | 2026-10-28 | 有来源 | 存档 497 B |
| 2 | 12 条路由：`/ /account/model /account/security /admin/trials /assets /cases /kb /login /review /skills /tasks /workspaces` | 同上 | `_evidence/index-BU20CUYI.js` 中 `to:\`/…\`` 全量提取 | 2026-10-28 | 同上 | 原件 | 助手 | 2026-10-28 | 有来源 | 正则 `to:` + 反引号提取，去重后 12 条 |
| 3 | 侧边栏两段式数组：`[AI 工作台,我的任务,(审核中心),案件中心,知识库]` 与 `[企业资产,工作空间,能力中心,(试用申请)]` | 同上 | 同文件 `label:\`AI 工作台\`}` 起 520 字符 | 2026-10-28 | 同上 | 原件 | 助手 | 2026-10-28 | 有来源 | 审核中心/试用申请为条件渲染 |
| 4 | 权限驱动：`e.permissions.review` / `e.permissions.admin` 决定是否渲染并带 badge | 同上 | 同上片段 | 2026-10-28 | 同上 | 原件 | 助手 | 2026-10-28 | 有来源 | — |
| 5 | `[data-theme=light]` / `[data-theme=dark]` 两套令牌；`--material:#fafcfdd1` / `#2a2e34f7` / `#1b1f24db` | 同上 | `_evidence/index-D8rLeU-F.css` 主题块 | 2026-10-28 | 同上 | 原件 | 助手 | 2026-10-28 | 有来源 | — |
| 6 | `--glass-line:transparent`、`--surface:#ffffff80`、`--shadow-lift:0 8px 20px -8px #141e3033,0 28px 64px -18px #141e3057` | 同上 | 同上（light 块） | 2026-10-28 | 同上 | 原件 | 助手 | 2026-10-28 | 有来源 | — |
| 7 | 四条玻璃规则（顶栏 16px/菜单 24px/对话框 30px/遮罩 4px） | 同上 | CSS 规则原文 | 2026-10-28 | 同上 | 原件 | 助手 | 2026-10-28 | 有来源 | 逐条抄录，未改写数值 |
| 8 | `backdrop-filter` 规则 28 条，开启 16、`none` 12 | 同上 | 正则 `backdrop-filter:(?:blur\|saturate)` 计数 32（含 `-webkit-` 副本）、`backdrop-filter:none` 计数 24 | 2026-10-28 | 同上 | 原件（本地统计） | 助手 | 2026-10-28 | 有来源 | 见复校记录第 2 项：初稿数字有误，已改 |
| 9 | 语义色三档 `--rose:#e9a197/…`；尺度 `radius 10/16/24/28/pill`、`space 4/8/12/16/24/32`、`fs 36/30/16/14/12`、`--ipw-ease:cubic-bezier(.2,.8,.2,1)` | 同上 | `:root` 与 light 主题块 | 2026-10-28 | 同上 | 原件 | 助手 | 2026-10-28 | 有来源 | — |
| 10 | `--canvas-bg` 四层 radial-gradient（light 版数值） | 同上 | light 主题块首行 | 2026-10-28 | 同上 | 原件 | 助手 | 2026-10-28 | 有来源 | — |

## 待补 / 不可得

| 项 | 状态 | 说明 |
|---|---|---|
| 登录后的实际页面、交互、任务状态机 | 待补 | 需浏览器控制或页面截图；本会话未使用 admin 账号，未做任何登录尝试 |
| 后端数据模型 | 不可得 | 前端包不含 |
| 「内置法规库 3.4 万+ 条」 | 不可得 | 界面宣传文案，无法核实口径 |

## 状态定义

- **有来源**：已定位到来源原处并核对一致。
- **待补**：知道需要什么数据，但尚未取得来源；须写明缺什么。
- **不可得**：已尝试获取而无法取得；须写明尝试途径与原因。
