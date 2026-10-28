import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

export default function Register() {
  const { register, user } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to="/app" replace />

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await register(email.trim(), password)
      navigate('/app')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <Link className="brand" to="/"><span className="brand-mark">L</span><span className="brand-name">LawLens</span></Link>
        <h1>创建账号</h1>
        <p className="muted">注册即赠 100 积分，一次核查消耗 10 积分。</p>
        <form onSubmit={submit}>
          <label>邮箱<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
          <label>密码（至少 6 位）<input type="password" value={password} minLength={6} onChange={(e) => setPassword(e.target.value)} required /></label>
          {error && <div className="alert error">{error}</div>}
          <button className="btn primary block" disabled={busy}>{busy ? '创建中…' : '注册'}</button>
        </form>
        <p className="muted center">已有账号？<Link to="/login">登录</Link></p>
      </div>
    </div>
  )
}
