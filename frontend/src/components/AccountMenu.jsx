import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { api } from '../api'

function initialsOf(email) {
  const name = String(email || '').split('@')[0]
  return (name[0] || '?').toUpperCase()
}

function formatTime(value) {
  if (!value) return ''
  const text = String(value).replace('T', ' ')
  return text.length >= 16 ? text.slice(0, 16) : text
}

function Modal({ title, onClose, children }) {
  useEffect(() => {
    const onKey = (event) => { if (event.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="am-overlay"
      onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}
    >
      <div className="am-modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="am-modal-head">
          <h3>{title}</h3>
          <button className="am-x" onClick={onClose} aria-label="关闭">×</button>
        </div>
        {children}
      </div>
    </div>
  )
}

function PasswordDialog({ onClose }) {
  const [form, setForm] = useState({ old: '', next: '', confirm: '' })
  const [msg, setMsg] = useState({ type: '', text: '' })
  const [busy, setBusy] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    if (form.next !== form.confirm) {
      setMsg({ type: 'error', text: '两次输入的新密码不一致' })
      return
    }
    setBusy(true)
    setMsg({ type: '', text: '' })
    try {
      await api.changePassword(form.old, form.next)
      setForm({ old: '', next: '', confirm: '' })
      setMsg({ type: 'info', text: '密码已修改，下次登录请使用新密码。' })
    } catch (err) {
      setMsg({ type: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title="修改密码" onClose={onClose}>
      <form className="settings-form" onSubmit={submit}>
        <label>原密码
          <input type="password" value={form.old} autoComplete="current-password"
            onChange={(e) => setForm({ ...form, old: e.target.value })} required />
        </label>
        <label>新密码（至少 6 位）
          <input type="password" minLength={6} value={form.next} autoComplete="new-password"
            onChange={(e) => setForm({ ...form, next: e.target.value })} required />
        </label>
        <label>确认新密码
          <input type="password" minLength={6} value={form.confirm} autoComplete="new-password"
            onChange={(e) => setForm({ ...form, confirm: e.target.value })} required />
        </label>
        {msg.text && <div className={`alert ${msg.type}`}>{msg.text}</div>}
        <div className="actions">
          <button className="btn primary" disabled={busy}>{busy ? '提交中…' : '确认修改'}</button>
          <button type="button" className="btn ghost" onClick={onClose}>关闭</button>
        </div>
      </form>
    </Modal>
  )
}

function CreditsDialog({ onClose }) {
  const [state, setState] = useState({ loading: true, error: '', credits: null, items: [] })

  useEffect(() => {
    let alive = true
    api.credits()
      .then((data) => {
        if (!alive) return
        setState({ loading: false, error: '', credits: data.credits ?? 0, items: data.items || [] })
      })
      .catch((err) => {
        if (!alive) return
        setState({ loading: false, error: err.message, credits: null, items: [] })
      })
    return () => { alive = false }
  }, [])

  return (
    <Modal title="积分查询" onClose={onClose}>
      {state.loading && <p className="muted">读取中…</p>}
      {state.error && <div className="alert error">{state.error}</div>}
      {!state.loading && !state.error && (
        <>
          <div className="am-balance">
            <span className="muted small">当前积分</span>
            <b>{state.credits}</b>
          </div>
          {state.items.length === 0 ? (
            <p className="muted small">还没有积分流水。发起一次核查后会在这里留下记录。</p>
          ) : (
            <ul className="am-ledger">
              {state.items.map((item, index) => (
                <li key={`${item.created_at}-${index}`}>
                  <span className="am-ledger-reason">
                    {item.reason}
                    {item.project_id ? <span className="muted small"> · 项目 #{item.project_id}</span> : null}
                  </span>
                  <span className="am-ledger-time muted small">{formatTime(item.created_at)}</span>
                  <span className={`am-ledger-delta ${item.delta >= 0 ? 'up' : 'down'}`}>
                    {item.delta >= 0 ? `+${item.delta}` : item.delta}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="muted small">每次核查扣减的积分以运行时的规则为准；失败任务会原额退回。</p>
        </>
      )}
      <div className="actions">
        <button className="btn ghost" onClick={onClose}>关闭</button>
      </div>
    </Modal>
  )
}

export default function AccountMenu() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [dialog, setDialog] = useState(null)
  const boxRef = useRef(null)

  const letter = useMemo(() => initialsOf(user?.email), [user?.email])
  const isAdmin = user?.role === 'admin'

  useEffect(() => {
    if (!open) return
    const onDown = (event) => {
      if (!boxRef.current || !boxRef.current.contains(event.target)) setOpen(false)
    }
    const onKey = (event) => { if (event.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const pick = (next) => {
    setOpen(false)
    setDialog(next)
  }

  const signOut = async () => {
    setOpen(false)
    await logout()
    navigate('/')
  }

  return (
    <div className="account" ref={boxRef}>
      <button
        className={`account-trigger ${open ? 'on' : ''}`}
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="账号菜单"
      >
        <span className="account-avatar" aria-hidden="true">{letter}</span>
      </button>

      {open && (
        <div className="account-menu" role="menu">
          <div className="account-head">
            <span className="account-avatar lg" aria-hidden="true">{letter}</span>
            <div className="account-id">
              <div className="account-email" title={user?.email}>{user?.email}</div>
              <div className="account-meta">
                <span className={`account-chip ${isAdmin ? 'admin' : ''}`}>{isAdmin ? '管理员' : '普通用户'}</span>
                <span className="muted small">积分 {user?.credits ?? 0}</span>
              </div>
            </div>
          </div>

          <div className="account-split" />

          <button className="account-item" role="menuitem" onClick={() => pick('credits')}>
            <span className="account-item-label">积分查询</span>
            <span className="muted small">{user?.credits ?? 0}</span>
          </button>
          <button className="account-item" role="menuitem" onClick={() => pick('password')}>
            <span className="account-item-label">修改密码</span>
          </button>
          <button className="account-item" role="menuitem" onClick={() => { setOpen(false); navigate('/app/settings') }}>
            <span className="account-item-label">设置</span>
          </button>

          <div className="account-split" />

          <button className="account-item danger" role="menuitem" onClick={signOut}>
            <span className="account-item-label">退出登录</span>
          </button>
        </div>
      )}

      {dialog === 'password' && <PasswordDialog onClose={() => setDialog(null)} />}
      {dialog === 'credits' && <CreditsDialog onClose={() => setDialog(null)} />}
    </div>
  )
}
