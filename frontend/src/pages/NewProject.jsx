import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'

export default function NewProject() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    title: '',
    subject_name: '',
    brief: '',
    board: 'all',
    is_demo: true,
  })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const { id } = await api.createProject(form)
      navigate(`/app/p/${id}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page narrow">
      <div className="page-head">
        <div>
          <h1>新建核查</h1>
          <p className="muted">先建项目，下一步上传材料并启动核查。</p>
        </div>
      </div>

      <form className="form-card" onSubmit={submit}>
        <div className="field-static">
          <span className="field-label">核查范围</span>
          <span className="dim-chip">资产权属与经营基础</span>
          <span className="dim-chip">劳动用工合规</span>
          <span className="dim-chip">投资退出与股权回购</span>
          <span className="hint">每次核查固定覆盖三个维度，不再单独选择知识库。</span>
        </div>

        <label>项目名称
          <input value={form.title} onChange={set('title')} placeholder="例：某公司 港股IPO 资产核查" required />
        </label>

        <label>拟上市主体全称
          <input value={form.subject_name} onChange={set('subject_name')} placeholder="例：某某科技有限公司" />
          <span className="hint">用于判断权证权利人是否为主体本身，建议填写工商全称。</span>
        </label>

        <label>核查目标（自然语言）
          <textarea rows={4} value={form.brief} onChange={set('brief')}
            placeholder="例：核查核心厂房、土地权属是否清晰，租赁场地是否合法，经营资质是否在有效期内" />
          <span className="hint">系统会把它转成结构化任务单，并在执行前检查材料是否齐全。</span>
        </label>

        <label className="checkbox">
          <input type="checkbox" checked={form.is_demo} onChange={set('is_demo')} />
          标记为演示项目（报告中会加"虚构测试样本"横幅）
        </label>

        {error && <div className="alert error">{error}</div>}
        <button className="btn primary" disabled={busy}>{busy ? '创建中…' : '创建并进入'}</button>
      </form>
    </div>
  )
}
