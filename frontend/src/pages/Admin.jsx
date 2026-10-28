import { useEffect, useState } from 'react'
import { api } from '../api'

export default function Admin() {
  const [tab, setTab] = useState('overview')
  const [overview, setOverview] = useState(null)
  const [users, setUsers] = useState([])
  const [rules, setRules] = useState(null)
  const [logs, setLogs] = useState([])
  const [error, setError] = useState('')

  const loadOverview = () => api.overview().then(setOverview).catch((e) => setError(e.message))
  const loadUsers = () => api.users().then((d) => setUsers(d.users)).catch((e) => setError(e.message))
  const loadRules = () => api.rules().then((d) => setRules(d.rules)).catch((e) => setError(e.message))
  const loadLogs = () => api.audit().then((d) => setLogs(d.logs)).catch((e) => setError(e.message))

  useEffect(() => {
    loadOverview()
    loadUsers()
  }, [])

  useEffect(() => {
    if (tab === 'rules') loadRules()
    if (tab === 'audit') loadLogs()
  }, [tab])

  const adjust = async (id, delta) => {
    try {
      await api.addCredits(id, delta)
      await loadUsers()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>管理后台</h1>
          <p className="muted">用户与积分、核查要点库、审计日志。</p>
        </div>
      </div>

      {error && <div className="alert error">{error}</div>}

      <div className="tabs">
        {[['overview', '概览'], ['users', '用户与积分'], ['rules', '核查要点库'], ['audit', '审计日志']].map(([k, label]) => (
          <button key={k} className={`tab ${tab === k ? 'on' : ''}`} onClick={() => setTab(k)}>{label}</button>
        ))}
      </div>

      {tab === 'overview' && overview && (
        <div className="stats">
          <div className="stat"><b>{overview.users}</b><span>用户</span></div>
          <div className="stat"><b>{overview.projects}</b><span>项目</span></div>
          <div className="stat"><b>{overview.task_steps}</b><span>执行步骤</span></div>
          <div className="stat"><b>{overview.findings}</b><span>风险结论</span></div>
          <div className="stat"><b>{overview.credits_total}</b><span>积分总额</span></div>
          <div className="stat"><b>{overview.mock_mode ? '演示' : '在线'}</b><span>模型模式</span></div>
        </div>
      )}

      {tab === 'users' && (
        <table className="table">
          <thead><tr><th>ID</th><th>邮箱</th><th>角色</th><th>积分</th><th>操作</th></tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.id}</td>
                <td>{u.email}</td>
                <td>{u.role === 'admin' ? '管理员' : '用户'}</td>
                <td><b>{u.credits}</b></td>
                <td className="actions">
                  <button className="btn ghost sm" onClick={() => adjust(u.id, 100)}>+100</button>
                  <button className="btn ghost sm" onClick={() => adjust(u.id, -10)}>-10</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {tab === 'rules' && rules && (
        <section className="panel">
          <h2>资产权属与经营基础 · 核查要点（{rules.checkpoints.length}）</h2>
          <p className="muted small">{rules.note}</p>
          <table className="table rules-table">
            <thead><tr><th>编号</th><th>主题</th><th>核查要点</th><th>规范依据</th><th>状态</th></tr></thead>
            <tbody>
              {rules.checkpoints.map((c) => (
                <tr key={c.id}>
                  <td>{c.id}</td>
                  <td>{c.topic}</td>
                  <td className="small">{c.check_point}</td>
                  <td className="small muted">{c.rule_ref ? JSON.stringify(c.rule_ref) : '待补'}</td>
                  <td><span className={`badge ${c.verification_status === 'verified' ? 'green' : 'amber'}`}>
                    {c.verification_status === 'verified' ? '已核实' : '办案经验'}
                  </span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {tab === 'audit' && (
        <table className="table">
          <thead><tr><th>时间</th><th>操作者</th><th>动作</th><th>对象</th><th>详情</th></tr></thead>
          <tbody>
            {logs.map((l) => (
              <tr key={l.id}>
                <td className="small muted">{l.created_at?.replace('T', ' ')}</td>
                <td className="small">{l.email || '—'}</td>
                <td className="small">{l.action}</td>
                <td className="small">{l.target}</td>
                <td className="small muted">{l.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
