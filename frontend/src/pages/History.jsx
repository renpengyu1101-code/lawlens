import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { StatusBadge } from './Dashboard'

export default function History() {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api.projects()
      .then((d) => setProjects(d.projects || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>历史项目</h1>
          <p className="muted">过往每一次核查都在这里；点状态或「流程」可以看当时跑过的步骤。</p>
        </div>
        <Link className="btn ghost" to="/app">回透镜工作台</Link>
      </div>

      <section className="panel">
        {loading ? (
          <p className="muted">加载中…</p>
        ) : error ? (
          <div className="alert error">{error}</div>
        ) : projects.length === 0 ? (
          <p className="muted">还没有历史项目。回工作台写一句话就能开始。</p>
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
                    <Link to={`/app/p/${p.id}`} state={{ focusWorkflow: true }} className="badge-link" title="查看工作流程">
                      <StatusBadge status={p.status} />
                    </Link>
                  </td>
                  <td>{p.doc_count}</td>
                  <td>{p.finding_count}</td>
                  <td className="muted small">{p.updated_at?.replace('T', ' ').slice(0, 16)}</td>
                  <td className="row-actions">
                    <Link className="link-quiet" to={`/app/p/${p.id}`} state={{ focusWorkflow: true }}>流程</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
