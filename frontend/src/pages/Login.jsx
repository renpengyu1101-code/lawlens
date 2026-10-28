import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

export default function Login() {
  const { login, user } = useAuth()
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
      await login(email.trim(), password)
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
        <h1>登录</h1>
        <form onSubmit={submit}>
          <label>账号<input type="text" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="邮箱或 admin" required /></label>
          <label>密码<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          {error && <div className="alert error">{error}</div>}
          <button className="btn primary block" disabled={busy}>{busy ? '登录中…' : '登录'}</button>
        </form>
        <p className="muted center">还没有账号？<Link to="/register">注册</Link></p>
      </div>
    </div>
  )
}
