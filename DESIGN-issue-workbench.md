# 争议点工作台（NodeCite 式界面）· 后台需求分析

- 日期：2026-10-27
- 依据：用户提供的界面设计稿（股权投融资交易 / A公司增资文件核验）
- 结论：现有后台只能支撑其中约三分之一；这是一次数据模型的结构性升级，不是加几个接口

---

## 1. 界面里出现的对象（逐个控件的反推）

| 界面元素 | 背后必须存在的数据对象 |
|---|---|
| 案件标题、代理立场（投资方）、待审版本（股东协议 B）、当前状态（待律师复核） | 交易/案件元数据 + 立场 + 当前版本指针 + 案件状态机 |
| 左侧"材料与版本"：投资协议 A、股东协议 B·当前、历史审查意见 | 文档组（同一份文件的多版本）+ 版本标签 + 当前生效版本 |
| "原文段落 92"、"原文片段 · 协议 B" | 段落级切分与稳定段落 ID + 页码/偏移 + 原文引用 |
| 争议点："回购全额兑付期限是否缺失？" | 争议点（issue）对象：问题、主张、状态、严重度 |
| 处理步骤（材料定位→条款提取→历史意见比对→适用及逻辑核验→模型观点对照→律师复核） | 每争议点一张**步骤图（DAG）**：步骤类型（机器/人工）、依赖、状态、执行人 |
| "版本比对发现变化"、"发现变化"、"查看分歧" | 版本 diff 结果 + 模型/历史/律师多来源意见及其分歧 |
| 依据面板：原文匹配已定位 / 适用条件待核实 / 历史版本不作当前依据 / 律师确认未完成 | 每条证据的**四类状态**（匹配、适用范围、历史效力、人工确认） |
| "下一步：核对相关退出程序及义务主体" | 由步骤状态推导的待办建议（或人工填写） |
| 底部"本次变化" | 与上一版本相比的结论变化摘要（结论级 diff，不只是文字 diff） |
| "提交律师复核"按钮 | 复核工作流：承办核对 → 第二人复核 + 待办队列 + 通知 |
| 左侧"补充材料或问题 · 附到当前任务" | 评论/追问线程，可挂附件，绑定到争议点或案件 |
| "成果交付" | 复核意见书 / 差异报告等交付物的生成与版本 |
| 页脚"改版结构示意" | 这是设计稿标注，不是产品功能 |

## 2. 现有后台有什么、缺什么

**已有（可复用）**
- 项目（projects）、材料（documents）、结论（findings）、证据（citations）、质检（qc_runs）、报告（reports）、用户/积分/审计。
- 抽取与质检的判读逻辑、证据锚点机制。
- 文件解析（PDF/DOCX 分页）、docx 报告生成。

**缺失（这张图跑不起来的原因）**

1. **没有版本概念**：documents 是一次性上传，无法表达"A 版 / B 版 / 当前版"，更无法做版本比对。
2. **没有段落对象**：现在只有整篇文本 + 页码标记，"段落 92"这种定位做不到；高亮、跳转、稳定引用都缺基础。
3. **没有争议点对象**：findings 是流水线产出的一条结论，没有"问题/主张/状态/适用范围"这些字段，也不能挂步骤与意见。
4. **没有步骤图**：task_runs 是线性四段（A/B/C/D），不支持"每争议点一套 DAG"、人工步骤、依赖关系。
5. **没有人工复核状态机**：没有承办/复核两级、没有待办、没有确认留痕。
6. **没有多来源意见**：无法存"模型观点 vs 历史审查意见 vs 律师判断"并对照分歧。
7. **没有结论级 diff**：只有文本，没有"上一版结论是什么、这一版变成什么"。
8. **没有评论线程**：无法挂问题与补充材料。

## 3. 需要新增的数据模型

```
document_groups     (id, project_id, doc_type, title)                      文档组：投资协议 / 股东协议 / 历史意见
document_versions   (id, group_id, label, path, sha256, is_current, uploaded_by, created_at)
paragraphs          (id, version_id, ordinal, page, heading_path, text, char_start, char_end)
clauses             (id, version_id, clause_type, title, paragraph_ids, parties, amounts, dates,
                     conditions, confidence, anchor_paragraph_id)           条款级结构化
issues              (id, project_id, question, claim, status, severity, position, created_by, created_at)
issue_bases         (id, issue_id, version_id, paragraph_id, quote,
                     match_status, scope_status, history_status, lawyer_status)   依据面板四状态
issue_steps         (id, issue_id, step_key, name, kind, status, owner_id,
                     depends_on, output_json, started_at, finished_at)      步骤图节点
opinions            (id, issue_id, source, claim, reasoning, citations, created_at)  模型/历史/律师
reviews             (id, issue_id, stage, reviewer_id, decision, comment, created_at)
version_diffs       (id, from_version_id, to_version_id, change_type, paragraph_ids, summary)
conclusion_diffs    (id, project_id, from_version_id, to_version_id, issue_id, before, after)
comments            (id, project_id, issue_id, author_id, body, attachment_id, created_at)
deliverables        (id, project_id, kind, path, version, created_at)
```

要点：
- **版本不可变**：新版本只新增，不覆盖；`is_current` 单指针。
- **段落 ID 稳定**：同一文档跨版本尽量保持段落身份（用文本相似度对齐），否则"段落 92"在 B 版会失去意义。
- **issue_bases 四状态**是界面右栏的核心，必须落库而不是前端拼。

## 4. 需要新增的接口

```
GET  /api/projects/{id}/workbench        案件元数据 + 材料树 + 争议点列表（首屏一次拿全）
GET  /api/issues/{id}                    争议点详情：步骤图 + 依据 + 意见 + 复核状态
POST /api/projects/{id}/versions         上传新版本（同组内递增）
GET  /api/versions/{id}/diff/{other}     段落级 diff + 变化摘要
POST /api/issues/{id}/steps/{key}/run    触发机器步骤（材料定位/条款提取/比对/核验）
POST /api/issues/{id}/opinions           写入模型或律师意见
POST /api/issues/{id}/review             提交复核（stage=承办/复核，decision）
POST /api/issues/{id}/comments           补充事实/追问
POST /api/projects/{id}/deliverables     生成复核意见/差异报告
GET  /api/workbench/tasks?assignee=me    待办队列（提交复核后进入）
```

## 5. 流水线要改的地方

现在的流水线是"整份材料 → 一批风险项"，需要改成 **争议点驱动**：

1. **找争议点**：先由规则+模型提出候选争议点（例如"回购兑付期限是否载明"），而不是直接出风险。
2. **每争议点一张步骤图**：材料定位 → 条款提取 → 历史比对 → 适用性核验 → 模型对照 → 律师复核。
3. **证据要带四状态**：匹配（能否命中原文）、适用范围（本争议点是否适用）、历史效力（旧版意见是否仍有效）、人工确认。
4. **结论级 diff**：版本更新后要能回答"哪些争议点结论变了"。
5. **模型观点必须可对照**：同一争议点保留多来源意见，不覆盖、不合并。

## 6. 权限与留痕

- 角色：助理 / 承办律师 / 复核律师 / 管理员。
- 双人复核：承办确认后进入复核队列，复核人通过才算完成；两级都要留痕。
- 所有状态变更写审计（谁、何时、从什么改成什么）。
- 版本与意见**只增不改**，改错用新记录覆盖显示，不物理删除。

## 7. 实施顺序建议

| 阶段 | 内容 | 依赖 |
|---|---|---|
| P0 | 版本模型 + 段落切分 + 争议点对象 + 四状态依据 | 无，先做 |
| P1 | 步骤图（DAG）+ 人工步骤 + 复核状态机 + 待办 | P0 |
| P2 | 版本 diff + 结论级 diff + 多来源意见对照 | P0 |
| P3 | 评论/追问、交付物生成、通知 | P1/P2 |

## 8. 与现有代码的衔接

- `documents` 迁移为 `document_versions`（保留原字段，加 group/label/is_current）。
- `findings` 升级为 `issues`（补 question/claim/status/severity/position）。
- `citations` 升级为 `issue_bases`（补四状态 + paragraph_id）。
- `task_runs` 升级为 `issue_steps`（补 depends_on/kind/owner）。
- 四个 agent 保留，但调用点从"整案"改为"按争议点"。

> 说明：本文件是对设计稿的结构化分析，不含界面实现；界面本身仍需另行开发。
