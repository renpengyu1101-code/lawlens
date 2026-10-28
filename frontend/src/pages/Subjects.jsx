import { useEffect, useState } from 'react'
import { api } from '../api'

export default function Subjects() {
  const [list, setList] = useState([])
  const [active, setActive] = useState('')
  const [score, setScore] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.subjects()
      .then((d) => {
        setList(d.subjects || [])
        if (d.subjects?.length) setActive(d.subjects[0].subject)
      })
      .catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    if (!active) return
    setScore(null)
    api.subjectScore(active).then(setScore).catch((e) => setError(e.message))
  }, [active])

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>主体总表</h1>
          <p className="muted">同一家公司跑完三个板块后合成 100 分总表；未建立的板块记 N/A。</p>
        </div>
      </div>

      {error && <div className="alert error">{error}</div>}

      {list.length === 0 ? (
        <p className="muted">还没有填写拟上市主体名称的项目。</p>
      ) : (
        <div className="subject-list">
          {list.map((s) => (
            <button
              key={s.subject}
              className={`subject-item ${active === s.subject ? 'on' : ''}`}
              onClick={() => setActive(s.subject)}
            >
              <b>{s.subject}</b>
              <span className="muted small">{s.boards.join(' / ')} · {s.projects} 个项目</span>
            </button>
          ))}
        </div>
      )}

      {score && (
        <section className="panel">
          <h2>
            {score.subject}
            <span className="muted small" style={{ marginLeft: 10 }}>
              覆盖 {Math.round((score.coverage || 0) * 100)}%
            </span>
          </h2>
          <p className="small">
            已核查部分 {score.on_checked}/100（折合总分 {score.normalized}）；
            等级 {score.grade === '—' ? '暂不定级（覆盖不足）' : score.grade}
          </p>
          {score.dimensions.map((d) => (
            <div className="score-row" key={d.id}>
              <span className="score-name">{d.name}</span>
              <span className="score-bar">
                <i style={{ width: d.applicable ? `${(d.earned / d.applicable) * 100}%` : '0%' }} />
              </span>
              <span className="score-val">
                {d.applicable ? `${d.earned} / ${d.applicable}` : 'N/A'}
              </span>
            </div>
          ))}
          <p className="muted small">{score.note}</p>
        </section>
      )}
    </div>
  )
}
