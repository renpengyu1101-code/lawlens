import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import AttachmentList from '../components/AttachmentList'
import CheckProgress from '../components/CheckProgress'
import ConfirmDialog from '../components/ConfirmDialog'
import { llmHeaders } from '../settings'

export const STATUS = {
  draft: ['草稿', 'gray'],
  running: ['执行中', 'blue'],
  awaiting_materials: ['待补材料', 'amber'],
  pending_review: ['待律师复核', 'amber'],
  needs_rework: ['退回整改', 'red'],
  done: ['已出报告', 'green'],
  failed: ['执行失败', 'red'],
}

export function StatusBadge({ status }) {
  const [label, tone] = STATUS[status] || [status, 'gray']
  return <span className={`badge ${tone}`}>{label}</span>
}

const FLOW = [
  ['意图识别', '把问题转成核查任务单'],
  ['资料抽取', '逐页提取字段并标注出处'],
  ['风险分析', '按要点判读风险等级'],
  ['质检', '每条结论回原文核对'],
  ['报告', '生成可下载的 docx'],
]

export default function Dashboard() {
  const { refresh } = useAuth()
  const navigate = useNavigate()
  const fileRef = useRef(null)

  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [question, setQuestion] = useState('')
  const [subject, setSubject] = useState('')
  const [files, setFiles] = useState([])
  const [uploadProgress, setUploadProgress] = useState(null)
  const [busy, setBusy] = useState(false)
  const [runId, setRunId] = useState(null)
  const [pendingDelete, setPendingDelete] = useState(null)

  useEffect(() => {
    api.projects()
      .then((d) => setProjects(d.projects))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const pickFiles = (e) => {
    // Snapshot before clearing the input; React may execute the updater later.
    const selected = Array.from(e.target.files || [])
    if (!selected.length) return
    setUploadProgress(null)
    setFiles((prev) => [...prev, ...selected])
    if (fileRef.current) fileRef.current.value = ''
  }

  const send = async () => {
    if (!question.trim()) {
      setError('请先描述要核查的问题')
      return
    }
    setBusy(true)
    setError('')
    setUploadProgress({ phase: 'creating' })
    try {
      const q = question.trim()
      const title = q.length > 26 ? `${q.slice(0, 26)}…` : q
      const { id } = await api.createProject({
        title,
        subject_name: subject.trim(),
        brief: q,
        board: 'all',          // 固定三维度全面核查，不再由用户挑选知识库
        is_demo: true,
      })
      if (files.length) await api.upload(id, files, setUploadProgress)
      await refresh().catch(() => {})
      setUploadProgress(null)
      await api.run(id, llmHeaders())   // 建完立刻起跑，进度就地显示
      setRunId(id)
      api.projects().then((d) => setProjects(d.projects)).catch(() => {})
    } catch (err) {
      setUploadProgress({ phase: 'error' })
      setError(err.message)
      setBusy(false)
    }
  }

  const removeProject = (p) => setPendingDelete(p)

  const confirmDelete = async () => {
    const target = pendingDelete
    if (!target) return
    setPendingDelete(null)
    try {
      await api.deleteProject(target.id)
      setProjects((prev) => prev.filter((x) => x.id !== target.id))
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>透镜工作台</h1>
          <p className="muted">把你的问题，交给透镜。</p>
        </div>
      </div>

      <div className="workflow">
        {FLOW.map(([name, desc], i) => (
          <div className="flow-step" key={name}>
            <span className="flow-index">{i + 1}</span>
            <div>
              <div className="flow-name">{name}</div>
              <div className="flow-desc">{desc}</div>
            </div>
          </div>
        ))}
      </div>

      {runId ? (
        <CheckProgress
          projectId={runId}
          onOpen={() => navigate(`/app/p/${runId}`)}
          onReset={() => { setRunId(null); setQuestion(''); setFiles([]); setUploadProgress(null); setBusy(false) }}
          onSettled={() => api.projects().then((d) => setProjects(d.projects)).catch(() => {})}
        />
      ) : (
        <section className="composer">
          <textarea
            rows={4}
            placeholder="例：我想评估一下我们公司港股上市可能性"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <div className="composer-row">
            <label className="composer-field">
              拟上市主体
              <input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="主体全称（选填）" />
            </label>
            <div className="composer-actions">
              <button className="btn ghost" onClick={() => fileRef.current?.click()} disabled={busy}>＋ 附件</button>
              <button className="btn primary send" onClick={send} disabled={busy}>
                {busy ? (uploadProgress?.phase === 'creating' ? '正在建立项目…' : '正在上传附件…') : '开始核查'}
              </button>
            </div>
          </div>
          <input ref={fileRef} type="file" multiple hidden onChange={pickFiles} />
          <AttachmentList files={files} progress={uploadProgress} disabled={busy}
            onRemove={(i) => { setFiles((prev) => prev.filter((_, idx) => idx !== i)); setUploadProgress(null) }} />
          {error && <div className="alert error">{error}</div>}
        </section>
      )}

      <section className="panel">
        <h2>最近项目</h2>
        {loading ? (
          <p className="muted">加载中…</p>
        ) : projects.length === 0 ? (
          <p className="muted">还没有项目。上面写一句话就能开始。</p>
        ) : (
          <table className="table">
            <thead>
              <tr><th>项目</th><th>主体</th><th>状态</th><th>材料</th><th>风险项</th><th>更新时间</th><th>操作</th></tr>
            </thead>
            <tbody>
              {projects.map((p) => (
                <tr key={p.id}>
                  <td><Link to={`/app/p/${p.id}`}>{p.title}</Link></td>
                  <td className="muted">{p.subject_name || '—'}</td>
                  <td>
                    <Link
                      to={`/app/p/${p.id}`}
                      state={{ focusWorkflow: true }}
                      className="badge-link"
                      title="查看工作流程"
                    >
                      <StatusBadge status={p.status} />
                    </Link>
                  </td>
                  <td>{p.doc_count}</td>
                  <td>{p.finding_count}</td>
                  <td className="muted small">{p.updated_at?.replace('T', ' ').slice(0, 16)}</td>
                  <td className="row-actions">
                    <Link className="link-quiet" to={`/app/p/${p.id}`} state={{ focusWorkflow: true }}>流程</Link>
                    <button className="link-danger" onClick={() => removeProject(p)}>删除</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <ConfirmDialog
        open={!!pendingDelete}
        title="删除这个项目？"
        message={pendingDelete ? `「${pendingDelete.title}」` : ''}
        detail="风险清单、证据、报告与材料记录会一并删除，且无法恢复。"
        confirmText="删除"
        danger
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  )
}
