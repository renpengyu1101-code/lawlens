import { Navigate, Route, Routes, Link, useLocation } from 'react-router-dom'
import { useAuth } from './auth'
import AccountMenu from './components/AccountMenu'
import SiteFooter from './components/SiteFooter'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import NewProject from './pages/NewProject'
import History from './pages/History'
import ProjectDetail from './pages/ProjectDetail'
import Admin from './pages/Admin'
import Settings from './pages/Settings'
import Subjects from './pages/Subjects'

const NAV = [
  { to: '/app', label: '透镜工作台', exact: true },
  { to: '/app/history', label: '历史项目' },
  { to: '/app/subjects', label: '主体总表' },
]

function Layout({ children }) {
  const { user } = useAuth()
  const location = useLocation()
  const isAdmin = user?.role === 'admin'

  return (
    <div className="shell">
      <header className="topbar">
        <Link className="brand" to="/app">
          <span className="brand-mark">L</span>
          <span className="brand-name">LawLens</span>
        </Link>
        <nav className="nav">
          {NAV.map((item) => {
            const active = item.exact ? location.pathname === item.to : location.pathname.startsWith(item.to)
            return <Link key={item.to} className={active ? 'active' : ''} to={item.to}>{item.label}</Link>
          })}
          {isAdmin && <Link className={location.pathname === '/admin' ? 'active' : ''} to="/admin">管理后台</Link>}
        </nav>
        <AccountMenu />
      </header>
      <main className="content">{children}</main>
      <SiteFooter />
    </div>
  )
}

function Guard({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="center muted">加载中…</div>
  if (!user) return <Navigate to="/login" replace />
  return <Layout>{children}</Layout>
}

function AdminOnly({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="center muted">加载中…</div>
  if (!user) return <Navigate to="/login" replace />
  if (user.role !== 'admin') return <Navigate to="/app" replace />
  return <Layout>{children}</Layout>
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/app" element={<Guard><Dashboard /></Guard>} />
      <Route path="/app/history" element={<Guard><History /></Guard>} />
      {/* 新建核查入口已从导航移除，保留路由以兼容旧链接 */}
      <Route path="/app/new" element={<Guard><NewProject /></Guard>} />
      <Route path="/app/p/:id" element={<Guard><ProjectDetail /></Guard>} />
      <Route path="/app/settings" element={<Guard><Settings /></Guard>} />
      <Route path="/app/subjects" element={<Guard><Subjects /></Guard>} />
      <Route path="/admin" element={<AdminOnly><Admin /></AdminOnly>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
