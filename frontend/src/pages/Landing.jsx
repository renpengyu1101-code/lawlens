import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

// 风险提示语句：均为核查要点的一般化表述，不指向任何真实企业
const LINES = [
  '核心资产权属未过户',
  '土地使用权已设定抵押',
  '经营场所出租方非产权人',
  '经营资质有效期已届满',
  '专利由自然人持有',
  '商标专用权已质押',
  '社保缴纳基数与工资表不一致',
  '对赌回购义务尚未清理',
  '主要设备存在融资租赁',
  '在建工程尚未竣工验收',
  '划拨土地未办理出让手续',
  '租赁期限短于申报周期',
  '许可范围未覆盖新增业务',
  '职务发明归属约定缺失',
  '关联方占用核心资产',
  '权证记载与账面记录不符',
  '劳务派遣比例超出岗位范围',
  '未签书面劳动合同人员 8 人',
  '社会保险缴纳人数少于在职人数',
  '竞业限制未约定补偿',
  '历史仲裁案件尚未结案',
  '认缴出资尚未实缴到位',
  '股东之间存在股权代持',
  '投资协议中的回购义务未终止',
]

// 八枚透镜：位置与初速度各不相同，彼此弹性碰撞
const LENS_DEFS = [
  { r: 132, k: 1.18 }, { r: 96, k: 1.12 }, { r: 150, k: 1.22 }, { r: 78, k: 1.14 },
  { r: 118, k: 1.20 }, { r: 88, k: 1.12 }, { r: 140, k: 1.16 }, { r: 104, k: 1.24 },
]

const MARGIN = 60 // 允许越出文字场边界，扩大活动范围

export default function Landing() {
  const { user, login, logout } = useAuth()
  const navigate = useNavigate()
  const scene = useRef(null)
  const copies = useRef([])
  const inners = useRef([])
  const rings = useRef([])

  const [account, setAccount] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const el = scene.current
    if (!el) return

    let W = 0
    let H = 0
    const measure = () => {
      const rect = el.getBoundingClientRect()
      W = rect.width || el.clientWidth
      H = rect.height || el.clientHeight
    }
    measure()
    window.addEventListener('resize', measure)

    const bodies = LENS_DEFS.map((d, i) => ({
      ...d,
      x: W * (0.18 + 0.64 * ((i * 0.37) % 1)),
      y: H * (0.18 + 0.64 * ((i * 0.61) % 1)),
      vx: 120 * Math.cos(i * 2.4 + 0.6),
      vy: 120 * Math.sin(i * 1.7 + 1.1),
    }))

    // 每枚透镜：裁一个圆，圆内放一份以「圆心上那一点」为原点放大的内容副本
    const render = () => {
      bodies.forEach((b, i) => {
        const copy = copies.current[i]
        const inner = inners.current[i]
        const ring = rings.current[i]
        if (!copy || !inner) return

        copy.style.left = `${b.x - b.r}px`
        copy.style.top = `${b.y - b.r}px`
        copy.style.width = `${b.r * 2}px`
        copy.style.height = `${b.r * 2}px`

        inner.style.left = `${b.r - b.x}px`
        inner.style.top = `${b.r - b.y}px`
        inner.style.width = `${W}px`
        inner.style.height = `${H}px`
        inner.style.transformOrigin = `${b.r}px ${b.r}px`
        inner.style.transform = `scale(${b.k})`

        if (ring) {
          ring.style.left = `${b.x - b.r}px`
          ring.style.top = `${b.y - b.r}px`
          ring.style.width = `${b.r * 2}px`
          ring.style.height = `${b.r * 2}px`
        }
      })
    }

    const step = (dt) => {
      // 位移
      for (const b of bodies) {
        b.x += b.vx * dt
        b.y += b.vy * dt
      }
      // 边界反弹（允许越出 60px）
      for (const b of bodies) {
        if (b.x - b.r < -MARGIN) { b.x = -MARGIN + b.r; b.vx = Math.abs(b.vx) }
        if (b.x + b.r > W + MARGIN) { b.x = W + MARGIN - b.r; b.vx = -Math.abs(b.vx) }
        if (b.y - b.r < -MARGIN) { b.y = -MARGIN + b.r; b.vy = Math.abs(b.vy) }
        if (b.y + b.r > H + MARGIN) { b.y = H + MARGIN - b.r; b.vy = -Math.abs(b.vy) }
      }
      // 两两弹性碰撞（质量按半径平方）
      for (let i = 0; i < bodies.length; i++) {
        for (let j = i + 1; j < bodies.length; j++) {
          const a = bodies[i]
          const b = bodies[j]
          let dx = b.x - a.x
          let dy = b.y - a.y
          let dist = Math.hypot(dx, dy)
          const min = a.r + b.r
          if (dist >= min) continue
          if (dist === 0) { dx = 0.01; dy = 0; dist = 0.01 }

          const nx = dx / dist
          const ny = dy / dist
          const overlap = min - dist
          const ma = a.r * a.r
          const mb = b.r * b.r
          const total = ma + mb

          a.x -= nx * overlap * (mb / total)
          a.y -= ny * overlap * (mb / total)
          b.x += nx * overlap * (ma / total)
          b.y += ny * overlap * (ma / total)

          const rvn = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny
          if (rvn > 0) continue // 正在分开，不再施力
          const impulse = -(1 + 0.96) * rvn / (1 / ma + 1 / mb)
          a.vx -= impulse * nx / ma
          a.vy -= impulse * ny / ma
          b.vx += impulse * nx / mb
          b.vy += impulse * ny / mb
        }
      }
      // 限速：避免越弹越快或完全停住
      for (const b of bodies) {
        const speed = Math.hypot(b.vx, b.vy)
        if (speed > 240) { b.vx *= 240 / speed; b.vy *= 240 / speed }
        if (speed < 70) { const s = 70 / (speed || 1); b.vx *= s; b.vy *= s }
      }
    }

    let raf
    let last = performance.now()
    const tick = (now) => {
      const dt = Math.min((now - last) / 1000, 0.033)
      last = now
      step(dt)
      render()
      raf = requestAnimationFrame(tick)
    }
    render()
    raf = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', measure)
    }
  }, [])

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(account.trim(), password)
      navigate('/app')
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="landing">
      <header className="landing-nav">
        <span className="brand">
          <span className="brand-mark">L</span>
          <span className="brand-name">LawLens</span>
        </span>
      </header>

      <main className="stage">
        <h1 className="stage-title">
          上市准备中的法律风险，<br />值得逐页核对。
        </h1>

        <div className="scene-wrap">
          <div className="lens-scene" ref={scene} aria-hidden="true">
            <div className="lens-text dim">
              {LINES.map((line, i) => <span key={i}>{line}</span>)}
            </div>

            {LENS_DEFS.map((p, i) => (
              <div key={i} className="lens-copy" ref={(node) => { copies.current[i] = node }}>
                <div className="lens-inner" ref={(node) => { inners.current[i] = node }}>
                  <div className="lens-text bright">
                    {LINES.map((line, j) => <span key={j}>{line}</span>)}
                  </div>
                </div>
              </div>
            ))}

            {LENS_DEFS.map((_, i) => (
              <span key={`ring-${i}`} className="lens-ring" ref={(node) => { rings.current[i] = node }} />
            ))}
          </div>

          <div className="auth-actions">
            {user ? (
              <div className="home-session">
                <p className="muted small">已登录：{user.email}</p>
                <Link className="btn primary block" to="/app">进入工作台 →</Link>
                <button className="home-register" onClick={() => logout()}>退出登录</button>
              </div>
            ) : (
              <form className="home-login" onSubmit={submit}>
                <input
                  aria-label="账号"
                  placeholder="账号"
                  autoComplete="username"
                  value={account}
                  onChange={(e) => setAccount(e.target.value)}
                  required
                />
                <input
                  aria-label="密码"
                  placeholder="密码"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
                {error && <div className="home-login-error">{error}</div>}
                <button className="btn primary block" disabled={busy}>{busy ? '登录中…' : '登录工作台'}</button>
                <Link className="home-register" to="/register">还没有账号？注册</Link>
              </form>
            )}
          </div>
        </div>
      </main>

      <footer className="footer">
        <span>机器辅助整理，不构成法律意见。</span>
        <span>LawLens</span>
      </footer>
    </div>
  )
}
