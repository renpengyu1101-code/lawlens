import { useState } from 'react'
import { api } from '../api'
import { THEMES, applyTheme, getTheme, loadApi, saveApi, loadExternal, saveExternal } from '../settings'

export default function Settings() {
  const stored = loadApi()
  const storedExt = loadExternal()
  const [theme, setTheme] = useState(getTheme())

  const [pwd, setPwd] = useState({ old: '', next: '', confirm: '' })
  const [pwdMsg, setPwdMsg] = useState({ type: '', text: '' })
  const [pwdBusy, setPwdBusy] = useState(false)

  const [apiCfg, setApiCfg] = useState({
    key: stored.key || '',
    model: stored.model || 'deepseek-chat',
    base: stored.base || 'https://api.deepseek.com',
  })
  const [apiMsg, setApiMsg] = useState({ type: '', text: '' })
  const [ext, setExt] = useState({
    qccKey: storedExt.qccKey || '',
    qccSecret: storedExt.qccSecret || '',
    provider: storedExt.provider || 'tavily',
    searchKey: storedExt.searchKey || '',
  })
  const [pinging, setPinging] = useState(false)

  const saveExtCfg = () => {
    saveExternal({
      qccKey: ext.qccKey.trim(),
      qccSecret: ext.qccSecret.trim(),
      provider: ext.provider,
      searchKey: ext.searchKey.trim(),
    })
    setApiMsg({ type: 'info', text: '外部数据源配置已保存到本浏览器。' })
  }

  const pickTheme = (id) => {
    setTheme(id)
    applyTheme(id)
  }

  const saveApiCfg = () => {
    saveApi({
      key: apiCfg.key.trim(),
      model: apiCfg.model.trim(),
      base: apiCfg.base.trim(),
    })
    setApiMsg({ type: 'info', text: '已保存到本浏览器。下次发起核查时生效。' })
  }

  const testApi = async () => {
    setPinging(true)
    setApiMsg({ type: '', text: '' })
    try {
      const r = await api.llmPing({
        key: apiCfg.key.trim(),
        model: apiCfg.model.trim(),
        base: apiCfg.base.trim(),
      })
      if (r.ok) {
        setApiMsg({ type: 'info', text: `连接成功，可用模型：${(r.models || []).slice(0, 5).join('、') || '（未返回列表）'}` })
      } else {
        setApiMsg({ type: 'error', text: `连接失败：${r.error}` })
      }
    } catch (err) {
      setApiMsg({ type: 'error', text: err.message })
    } finally {
      setPinging(false)
    }
  }

  const submitPassword = async (e) => {
    e.preventDefault()
    if (pwd.next !== pwd.confirm) {
      setPwdMsg({ type: 'error', text: '两次输入的新密码不一致' })
      return
    }
    setPwdBusy(true)
    setPwdMsg({ type: '', text: '' })
    try {
      await api.changePassword(pwd.old, pwd.next)
      setPwd({ old: '', next: '', confirm: '' })
      setPwdMsg({ type: 'info', text: '密码已修改，下次登录请使用新密码。' })
    } catch (err) {
      setPwdMsg({ type: 'error', text: err.message })
    } finally {
      setPwdBusy(false)
    }
  }

  return (
    <div className="page narrow">
      <div className="page-head">
        <div>
          <h1>设置</h1>
          <p className="muted">配色、登录密码与模型接入。</p>
        </div>
      </div>

      <section className="panel">
        <h2>配色</h2>
        <p className="muted small">只影响本机显示，不改变他人看到的样子。</p>
        <div className="theme-row">
          {THEMES.map((t) => (
            <button
              key={t.id}
              className={`theme-swatch ${theme === t.id ? 'on' : ''}`}
              onClick={() => pickTheme(t.id)}
            >
              <span className={`theme-dot ${t.id}`} />
              <span className="theme-name">{t.name}</span>
              <span className="muted">{t.desc}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="panel">
        <h2>修改密码</h2>
        <form onSubmit={submitPassword} className="settings-form">
          <label>原密码
            <input type="password" value={pwd.old} onChange={(e) => setPwd({ ...pwd, old: e.target.value })} required />
          </label>
          <label>新密码（至少 6 位）
            <input type="password" minLength={6} value={pwd.next} onChange={(e) => setPwd({ ...pwd, next: e.target.value })} required />
          </label>
          <label>确认新密码
            <input type="password" minLength={6} value={pwd.confirm} onChange={(e) => setPwd({ ...pwd, confirm: e.target.value })} required />
          </label>
          {pwdMsg.text && <div className={`alert ${pwdMsg.type}`}>{pwdMsg.text}</div>}
          <button className="btn primary" disabled={pwdBusy}>{pwdBusy ? '提交中…' : '修改密码'}</button>
        </form>
      </section>

      <section className="panel">
        <h2>模型接入（DeepSeek）</h2>
        <p className="muted small">
          不填则使用服务器环境变量的密钥；填入后只保存在本浏览器，随核查请求发送，不写入数据库。
        </p>
        <div className="settings-form">
          <label>API Key
            <input
              type="password"
              placeholder="sk-..."
              value={apiCfg.key}
              onChange={(e) => setApiCfg({ ...apiCfg, key: e.target.value })}
            />
          </label>
          <label>模型
            <input value={apiCfg.model} onChange={(e) => setApiCfg({ ...apiCfg, model: e.target.value })} />
          </label>
          <label>接口地址
            <input value={apiCfg.base} onChange={(e) => setApiCfg({ ...apiCfg, base: e.target.value })} />
          </label>
          {apiMsg.text && <div className={`alert ${apiMsg.type}`}>{apiMsg.text}</div>}
          <div className="actions">
            <button className="btn primary" onClick={saveApiCfg}>保存</button>
            <button className="btn ghost" onClick={testApi} disabled={pinging}>
              {pinging ? '测试中…' : '测试连接'}
            </button>
            <button
              className="btn ghost"
              onClick={() => { setApiCfg({ key: '', model: 'deepseek-chat', base: 'https://api.deepseek.com' }); saveApi({}); setApiMsg({ type: 'info', text: '已清除本机配置。' }) }}
            >
              清除
            </button>
          </div>
        </div>
      </section>

      <section className="panel">
        <h2>外部数据源（企查查 / 联网搜索）</h2>
        <p className="muted small">
          用于按主体名称核查工商信息与外部报道。密钥只存在本浏览器，随核查请求通过请求头发送，不写入数据库。
        </p>
        <div className="settings-form">
          <label>企查查 AppKey
            <input value={ext.qccKey} onChange={(e) => setExt({ ...ext, qccKey: e.target.value })} placeholder="开放平台账号安全页获取" />
          </label>
          <label>企查查 SecretKey
            <input type="password" value={ext.qccSecret} onChange={(e) => setExt({ ...ext, qccSecret: e.target.value })} />
          </label>
          <label>搜索服务商
            <select value={ext.provider} onChange={(e) => setExt({ ...ext, provider: e.target.value })}>
              <option value="tavily">Tavily</option>
              <option value="serper">Serper</option>
              <option value="bocha">Bocha（博查）</option>
            </select>
          </label>
          <label>搜索 API Key
            <input type="password" value={ext.searchKey} onChange={(e) => setExt({ ...ext, searchKey: e.target.value })} />
          </label>
          <div className="actions">
            <button className="btn primary" onClick={saveExtCfg}>保存外部配置</button>
            <button
              className="btn ghost"
              onClick={() => { setExt({ qccKey: '', qccSecret: '', provider: 'tavily', searchKey: '' }); saveExternal({}) }}
            >
              清除
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}
