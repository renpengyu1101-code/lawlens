import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { api } from '../api'
import { StatusBadge } from './Dashboard'
import { useAuth } from '../auth'
import { llmHeaders, externalHeaders } from '../settings'
import AttachmentList from '../components/AttachmentList'

const LEVEL = { high: ['高风险', 'red'], medium: ['中风险', 'amber'], low: ['低风险', 'gray'] }
const QC = {
  pass: ['质检通过', 'green'],
  fail: ['质检未通过', 'red'],
  insufficient: ['材料缺失，无法验证', 'amber'],
}
const FINDING_STATUS = { open: '待处理', accepted: '已采纳', rejected: '已排除', fixed: '已整改' }
const BOARD_LABEL = { asset: '资产权属与经营基础', labor: '劳动用工合规', equity: '投资退出与股权回购', all: '三维度全面核查' }
const DOC_STATUS = { ocr: 'OCR 识别', needs_ocr: '扫描件未识别', failed: '解析失败', unsupported: '格式不支持' }

export default function ProjectDetail() {
  const { id } = useParams()
  const location = useLocation()
  const reviewRef = useRef(null)
  const workflowRef = useRef(null)
  const [steps, setSteps] = useState([])
  const { user, refresh } = useAuth()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [note, setNote] = useState('')
  const [uploadFiles, setUploadFiles] = useState([])
  const [uploadProgress, setUploadProgress] = useState(null)
  const fileRef = useRef(null)
  const versionInput = useRef(null)
  const versionTarget = useRef(null)
  const [groups, setGroups] = useState([])
  const [diff, setDiff] = useState(null)
  const [score, setScore] = useState(null)

  const load = useCallback(async () => {
    try {
      const d = await api.project(id)
      setData(d)
      return d
    } catch (e) {
      setError(e.message)
      return null
    }
  }, [id])

  useEffect(() => { load() }, [load])

  // 从工作台点「待律师复核」跳进来时，滚到复核区块
  useEffect(() => {
    if (!data) return
    if (location.state?.focusReview && reviewRef.current) {
      reviewRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [data, location.state])

  // 从工作台/历史项目点状态跳进来时，滚到工作流程
  useEffect(() => {
    if (!data) return
    if (location.state?.focusWorkflow && workflowRef.current) {
      workflowRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [data, steps, location.state])

  // 工作流程：直接读后端步骤记录
  useEffect(() => {
    api.progress(id).then((d) => setSteps(d.steps || [])).catch(() => setSteps([]))
  }, [id, data?.project?.status])

  // 执行中轮询
  useEffect(() => {
    if (!data) return
    if (data.project.status !== 'running') return
    const timer = setInterval(load, 2000)
    return () => clearInterval(timer)
  }, [data, load])

  const loadVersions = useCallback(async () => {
    try {
      const d = await api.versions(id)
      setGroups(d.groups || [])
    } catch { /* 版本面板失败不影响主流程 */ }
  }, [id])

  useEffect(() => { loadVersions() }, [loadVersions])

  useEffect(() => {
    api.score(id).then(setScore).catch(() => setScore(null))
  }, [id, data?.project?.status])

  const upload = async (e) => {
    const files = Array.from(e.target.files || [])
    if (!files.length) return
    setBusy('upload')
    setError('')
    setNote('')
    setUploadFiles(files)
    setUploadProgress({ phase: 'uploading', percent: 0 })
    try {
      await api.upload(id, files, setUploadProgress)
      setNote(`已上传 ${files.length} 份材料`)
      await loadVersions()
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const pickVersionFile = (gid) => {
    versionTarget.current = gid
    versionInput.current?.click()
  }

  const uploadVersionFile = async (e) => {
    const file = e.target.files?.[0]
    const gid = versionTarget.current
    if (!file || !gid) return
    setBusy('version')
    setError('')
    setNote('')
    setUploadFiles([file])
    setUploadProgress({ phase: 'uploading', percent: 0 })
    try {
      const r = await api.uploadVersion(id, gid, file, setUploadProgress)
      const s = r.diff || { added: 0, removed: 0, changed: 0 }
      setNote(`已上传 ${r.label}：新增 ${s.added}、删除 ${s.removed}、修改 ${s.changed}`)
      await loadVersions()
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
      if (versionInput.current) versionInput.current.value = ''
    }
  }

  const compareVersions = async (group) => {
    const list = group.versions || []
    if (list.length < 2) return
    try {
      setDiff(await api.versionDiff(list[list.length - 2].id, list[list.length - 1].id))
    } catch (err) {
      setError(err.message)
    }
  }

  const run = async () => {
    setBusy('run')
    setError('')
    try {
      const r = await api.run(id, llmHeaders())
      setNote(`任务已启动，剩余积分 ${r.credits}（本次消耗 10）`)
      await refresh()
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
    }
  }

  const runExternal = async () => {
    setBusy('external')
    setError('')
    try {
      const r = await api.externalCheck(id, externalHeaders())
      setNote(`联网核查完成：企查查${r.qcc ? '已返回' : '未返回'}，搜索 ${r.searches?.length ?? 0} 组，线索 ${r.findings?.length ?? 0} 条`)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
    }
  }

  const decideReview = async (decision) => {
    const current = data?.review
    if (!current) return
    try {
      await api.reviewDecision(current.id, decision, decision === 'approved' ? '复核通过' : '退回整改')
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  const revise = async (fid, status) => {
    try {
      await api.revise(fid, status)
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  if (!data) return <div className="page"><p className="muted">{error || '加载中…'}</p></div>

  const { project, documents, findings, missing, qc, task_spec, report, review, external } = data
  const canRun = project.status !== 'running' && documents.length > 0

  return (
    <div className="page">
      <div className="crumbs"><Link to="/app">工作台</Link> / 项目 #{project.id}</div>

      <div className="page-head">
        <div>
          <h1>{project.title}</h1>
          <p className="muted">
            {BOARD_LABEL[project.board] || project.board} · {project.subject_name || '未填写主体名称'} · {project.status === 'pending_review' ? (
              <button
                type="button"
                className="badge-link as-button"
                title="跳到待复核内容"
                onClick={() => reviewRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
              >
                <StatusBadge status={project.status} />
              </button>
            ) : <StatusBadge status={project.status} />}
            {report.available && <> · 报告 v{report.version}</>}
          </p>
        </div>
        <div className="actions">
          <button className="btn ghost" onClick={() => fileRef.current?.click()} disabled={!!busy || project.status === 'running'}>
            {busy === 'upload' ? '上传中…' : '＋ 上传材料'}
          </button>
          <button className="btn ghost" onClick={runExternal} disabled={!!busy || !project.subject_name}>
            {busy === 'external' ? '核查中…' : '联网核查'}
          </button>
          <button className="btn primary" onClick={run} disabled={!canRun || !!busy}>
            {busy === 'run' ? '启动中…' : '开始核查（-10 积分）'}
          </button>
          {report.available && <a className="btn ghost" href={api.reportUrl(id)}>下载报告</a>}
        </div>
      </div>
      <input ref={fileRef} type="file" multiple hidden onChange={upload} />
      <AttachmentList files={uploadFiles} progress={uploadProgress} />

      {error && <div className="alert error">{error}</div>}
      {note && <div className="alert info">{note}</div>}
      {project.status === 'running' && (
        <div className="alert info">正在执行：意图识别 → 资料抽取 → 分析 → 质检，页面会自动刷新。</div>
      )}

      {score && (
        <section className="panel">
          <h2>
            量化评分
            <span className="muted small" style={{ marginLeft: 10 }}>
              覆盖 {Math.round((score.coverage || 0) * 100)}%
            </span>
          </h2>
          <p className="small">
            已核查部分 {score.on_checked}/100（折合总分 {score.normalized}）；
            等级 {score.grade === '—' ? '暂不定级（覆盖不足）' : score.grade}
          </p>
          {score.dimensions.map((d) => (
            <div className="score-row" key={d.id}>
              <span className="score-name">{d.name}</span>
              <span className="score-bar">
                <i style={{ width: d.applicable ? `${(d.earned / d.applicable) * 100}%` : '0%' }} />
              </span>
              <span className="score-val">
                {d.applicable ? `${d.earned} / ${d.applicable}` : 'N/A'}
              </span>
            </div>
          ))}
          <p className="muted small">{score.note}</p>
        </section>
      )}

      {steps.length > 0 && (
        <section className="panel" ref={workflowRef} id="workflow">
          <h2>工作流程（{steps.length} 步）</h2>
          <p className="muted small">这是本次核查实际跑过的步骤：先按维度取证，再判读、质检、出报告。</p>
          <ol className="runsteps static">
            {steps.map((s) => (
              <li key={s.id} className={`runstep ${s.status}`}>
                <span className={`rs-icon ${s.status === 'ok' ? 'ok' : s.status === 'warn' ? 'warn' : s.status === 'skip' ? 'skip' : s.status === 'fail' ? 'fail' : ''}`}>
                  {s.status === 'ok' ? '✓' : s.status === 'warn' ? '!' : s.status === 'skip' ? '–' : s.status === 'fail' ? '✕' : '·'}
                </span>
                <span className="rs-agent">{s.agent}</span>
                <span className="rs-text">
                  {s.board ? <span className="rs-board">{s.board}</span> : null}
                  {s.text}
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {review && (
        <section ref={reviewRef} id="review" className={`panel ${review.status === 'pending' ? 'warn' : 'ok'}`}>
          <h2>
            律师复核：
            {review.status === 'pending' ? '待复核' : review.status === 'approved' ? '已通过' : '已退回'}
          </h2>
          {review.status === 'pending' && (
            <p className="muted small">以下情形触发强制复核，律师确认前不得作为最终结论。</p>
          )}
          {review.status === 'pending' && user?.role === 'admin' && (
            <div className="actions" style={{ marginBottom: 12 }}>
              <button className="btn primary" onClick={() => decideReview('approved')}>复核通过</button>
              <button className="btn ghost" onClick={() => decideReview('rejected')}>退回整改</button>
            </div>
          )}
          {review.triggers.map((t) => (
            <div className="review-item" key={t.code}>
              <div className="review-head">
                <span className="badge amber">{t.category}</span>
                <b>{t.code} {t.title}</b>
              </div>
              <p className="small">{t.detail}</p>
              {t.evidence?.length > 0 && (
                <ul className="small muted">
                  {t.evidence.map((e, i) => <li key={i}>{e}</li>)}
                </ul>
              )}
            </div>
          ))}
          {review.comment && <p className="small muted">复核意见：{review.comment}</p>}
        </section>
      )}

      {external && (
        <section className="panel">
          <h2>联网核查（线索，未核实）</h2>
          <p className="muted small">
            主体：{external.subject} · 抓取时间 {external.created_at?.replace('T', ' ')}。
            外部信息只作线索，须回原始来源核实后才能写入结论。
          </p>
          {external.warnings?.length > 0 && (
            <div className="alert warn">{external.warnings.join('；')}</div>
          )}
          {external.payload?.qcc && (
            <table className="table">
              <tbody>
                {[
                  ['企业名称', external.payload.qcc.facts.name],
                  ['统一社会信用代码', external.payload.qcc.facts.credit_code],
                  ['法定代表人', external.payload.qcc.facts.legal_person],
                  ['登记状态', external.payload.qcc.facts.status],
                  ['成立日期', external.payload.qcc.facts.start_date],
                  ['注册资本', external.payload.qcc.facts.reg_capital],
                  ['注册地址', external.payload.qcc.facts.address],
                  ['上市状态', external.payload.qcc.facts.is_listed === '1'
                    ? `已上市 ${external.payload.qcc.facts.stock_code || ''}` : '未上市'],
                ].filter(([, v]) => v).map(([k, v]) => (
                  <tr key={k}><th style={{ width: 160 }}>{k}</th><td>{v}</td></tr>
                ))}
              </tbody>
            </table>
          )}
          {external.findings?.length > 0 && (
            <div style={{ marginTop: 12 }}>
              {external.findings.map((f, i) => (
                <div className={`ext-item ${f.level}`} key={`${f.code}-${i}`}>
                  <div>
                    <span className={`badge ${f.level === 'high' ? 'red' : f.level === 'medium' ? 'amber' : 'gray'}`}>
                      {f.level === 'high' ? '高' : f.level === 'medium' ? '中' : '低'}
                    </span>{' '}
                    <b>{f.code} {f.title}</b>
                  </div>
                  <p className="small">{f.detail}</p>
                  {f.source_url && (
                    <a className="small" href={f.source_url} target="_blank" rel="noreferrer">{f.source_url}</a>
                  )}
                  {f.snippet && <p className="muted small">{f.snippet}</p>}
                </div>
              ))}
            </div>
          )}
          {external.payload?.searches?.map((s, i) => (
            <details className="small" key={i} style={{ marginTop: 8 }}>
              <summary>搜索：{s.query}（{s.results?.length || 0} 条）</summary>
              <ul>
                {(s.results || []).map((r, j) => (
                  <li key={j}><a href={r.url} target="_blank" rel="noreferrer">{r.title || r.url}</a></li>
                ))}
              </ul>
            </details>
          ))}
        </section>
      )}

      {missing.length > 0 && (
        <section className="panel warn">
          <h2>缺少必要材料（{missing.length} 项）</h2>
          <p className="muted">以下材料未提供，相应核查项已暂停；补齐后重新发起即可。</p>
          <ul>
            {missing.map((m) => (
              <li key={m.material}><b>{m.material}</b> —— {m.needed_for}</li>
            ))}
          </ul>
        </section>
      )}

      <div className="grid-2">
        <section className="panel">
          <h2>材料（{documents.length}）</h2>
          {documents.length === 0 ? (
            <p className="muted">尚未上传。支持 PDF / DOCX / TXT，单文件不超过 20MB。</p>
          ) : (
            <ul className="filelist">
              {documents.map((d) => (
                <li key={d.id}>
                  <span className="file-ico">▤</span>
                  <span className="file-name">{d.filename}</span>
                  <span className="muted small">{d.pages ? `${d.pages} 页` : ''} {DOC_STATUS[d.status] ? `· ${DOC_STATUS[d.status]}` : ''}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel">
          <h2>任务单</h2>
          {task_spec ? (
            <>
              <p className="small"><b>目标：</b>{task_spec.objective}</p>
              <p className="small"><b>模式：</b>{task_spec.mode === 'mock' ? '演示模式（未接模型）' : '模型分析（DeepSeek）'}</p>
              <ul className="small">
                {task_spec.checks?.map((c) => <li key={c.id}>{c.id} {c.topic}</li>)}
              </ul>
            </>
          ) : <p className="muted">尚未生成任务单。</p>}
        </section>
      </div>

      <section className="panel">
        <h2>材料与版本</h2>
        <p className="muted small">同一份材料可上传多个版本；段落跨版本保持定位，便于比对变化。</p>
        {groups.length === 0 ? (
          <p className="muted">暂无版本记录。</p>
        ) : (
          <div className="vg-list">
            {groups.map((g) => (
              <div className="vg-row" key={g.id}>
                <div className="vg-title">{g.title}</div>
                <div className="vg-chips">
                  {(g.versions || []).map((v) => (
                    <span className={`chip ${v.is_current ? 'on' : ''}`} key={v.id}>
                      {v.label}{v.is_current ? ' · 当前' : ''}
                    </span>
                  ))}
                </div>
                <div className="vg-actions">
                  <button className="btn ghost sm" onClick={() => pickVersionFile(g.id)} disabled={!!busy || project.status === 'running'}>
                    {busy === 'version' ? '上传中…' : '上传新版本'}
                  </button>
                  {(g.versions || []).length > 1 && (
                    <button className="btn ghost sm" onClick={() => compareVersions(g)}>对比最近两版</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
        <input ref={versionInput} type="file" hidden onChange={uploadVersionFile} />

        {diff && (
          <div className="diff-box">
            <div className="diff-head">
              <b>{diff.from.label} → {diff.to.label}</b>
              <span className="muted small">
                新增 {diff.summary.added} · 删除 {diff.summary.removed} · 修改 {diff.summary.changed}
              </span>
              <button className="btn ghost sm" onClick={() => setDiff(null)}>收起</button>
            </div>
            {diff.items.length === 0 && <p className="muted small">两版内容一致。</p>}
            {diff.items.map((item, i) => (
              <div className={`diff-item ${item.kind}`} key={`${item.kind}-${i}`}>
                <span className="diff-kind">{item.kind === 'added' ? '新增' : item.kind === 'removed' ? '删除' : '修改'}</span>
                {item.kind !== 'added' && <div className="diff-old">{item.left?.text}</div>}
                {item.kind !== 'removed' && <div className="diff-new">{item.right?.text}</div>}
              </div>
            ))}
          </div>
        )}
      </section>

      {qc && (
        <section className={`panel ${qc.passed ? 'ok' : 'warn'}`}>
          <h2>质检结论：{qc.passed ? '通过' : '未通过'}</h2>
          <p className="small">核查 {JSON.parse(qc.detail).checked} 条结论，阻断项 {JSON.parse(qc.detail).failed} 条。</p>
          {JSON.parse(qc.detail).issues?.map((i) => (
            <div key={i.code} className="alert error">[{i.code}] {i.title}：{i.reason}</div>
          ))}
          {JSON.parse(qc.detail).notices?.map((i) => (
            <div key={i.code} className="alert warn">[{i.code}] {i.title}：{i.reason}</div>
          ))}
          {JSON.parse(qc.detail).note && <p className="muted small">注：{JSON.parse(qc.detail).note}</p>}
        </section>
      )}

      <section className="panel">
        <h2>风险清单（{findings.length}）</h2>
        {findings.length === 0 ? (
          <p className="muted">暂无结论。开始核查后，这里会按风险等级列出每条结论及其证据。</p>
        ) : (
          <div className="findings">
            {findings.map((f) => {
              const [lLabel, lTone] = LEVEL[f.risk_level] || [f.risk_level, 'gray']
              const [qLabel, qTone] = QC[f.qc] || ['未质检', 'gray']
              return (
                <article className="finding" key={f.id}>
                  <header>
                    <span className={`badge ${lTone}`}>{lLabel}</span>
                    <span className="finding-title">{f.title}</span>
                    <span className="muted small">{f.code}</span>
                    <span className={`badge ${qTone}`}>{qLabel}</span>
                    <span className="badge gray">{FINDING_STATUS[f.status]}</span>
                  </header>
                  <p><b>事实：</b>{f.fact}</p>
                  <p><b>依据：</b>{f.rule_id || '—'} {f.rule_ref || '（规范依据待补）'}</p>
                  <p><b>建议：</b>{f.advice}</p>
                  <div className="evidence">
                    <b>证据：</b>
                    {f.citations.filter((c) => c.document_id).length === 0 && (
                      <span className="muted">（无原文锚点：对应材料缺失，本条仅作补料提示）</span>
                    )}
                    {f.citations.filter((c) => c.document_id).map((c) => (
                      <blockquote key={c.id}>
                        《{c.filename}》第 {c.page} 页：「{c.quote}」
                      </blockquote>
                    ))}
                  </div>
                  <div className="finding-actions">
                    <button className="btn ghost sm" onClick={() => revise(f.id, 'accepted')}>采纳</button>
                    <button className="btn ghost sm" onClick={() => revise(f.id, 'rejected')}>排除</button>
                    <button className="btn ghost sm" onClick={() => revise(f.id, 'fixed')}>标记已整改</button>
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}
