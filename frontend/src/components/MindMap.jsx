/**
 * 思维导图式进度：核查任务从根节点向外展开成枝干与叶子。
 * 数据来自 /api/projects/{id}/progress 的 steps（按 board 分组）。
 */
const SHORT_BOARD = {
  资产权属与经营基础: '资产权属',
  劳动用工合规: '劳动用工',
  投资退出与股权回购: '股权回购',
  上市评估: '港股材料',
  汇总: '出报告',
}

function shortBoard(name) {
  if (!name) return '核查'
  return SHORT_BOARD[name] || name.slice(0, 4)
}

function toneOf(status) {
  if (status === 'running') return 'run'
  if (status === 'ok') return 'ok'
  if (status === 'warn') return 'warn'
  if (status === 'fail') return 'fail'
  if (status === 'skip') return 'skip'
  return 'wait'
}

function truncate(text, max = 13) {
  const s = String(text || '')
  return s.length > max ? `${s.slice(0, max)}…` : s
}

export default function MindMap({ steps, running }) {
  // 按 board 分组，保持出现顺序
  const groups = []
  const index = new Map()
  steps.forEach((s) => {
    const key = s.board || '汇总'
    if (!index.has(key)) {
      index.set(key, groups.length)
      groups.push({ name: key, steps: [] })
    }
    groups[index.get(key)].steps.push(s)
  })

  const rowH = 78
  const height = Math.max(240, groups.length * rowH + 60)
  const width = 960
  const cx = 74
  const cy = height / 2
  const groupX = 232
  const stepX0 = 352
  const stepGap = 150
  const maxSteps = Math.max(1, ...groups.map((g) => g.steps.length))

  const rows = groups.map((g, i) => {
    const y = groups.length === 1 ? cy : 44 + i * ((height - 88) / (groups.length - 1))
    return { ...g, y }
  })

  return (
    <div className="mindmap-wrap">
      <svg className="mindmap" viewBox={`0 0 ${width} ${height}`} role="img"
        aria-label={`核查进度导图，共 ${steps.length} 步`}>
        {/* 根节点 */}
        <g className="mm-root">
          <circle cx={cx} cy={cy} r="19" className="mm-root-core" />
          <circle cx={cx} cy={cy} r="27" className="mm-root-halo" />
          <text x={cx} y={cy + 4} className="mm-root-label">核查</text>
        </g>

        {rows.map((row, gi) => {
          const done = row.steps.filter((s) => s.status !== 'running')
          const active = row.steps.some((s) => s.status === 'running')
          const tone = active ? 'run' : done.length === row.steps.length ? 'ok' : 'wait'
          const curve = `M ${cx + 27} ${cy} C ${cx + 80} ${cy}, ${groupX - 70} ${row.y}, ${groupX - 34} ${row.y}`
          return (
            <g key={row.name} className={`mm-branch mm-${tone}`} style={{ animationDelay: `${gi * 90}ms` }}>
              <path d={curve} className="mm-link" pathLength="1" />
              <g transform={`translate(${groupX}, ${row.y})`}>
                <rect x="-34" y="-13" width="68" height="26" rx="13" className="mm-group-rect" />
                <text x="0" y="4" className="mm-group-label">{shortBoard(row.name)}</text>
              </g>

              {row.steps.map((s, si) => {
                const x = stepX0 + si * stepGap
                const tone2 = toneOf(s.status)
                const link = `M ${groupX + 34} ${row.y} C ${groupX + 70} ${row.y}, ${x - 60} ${row.y}, ${x - 13} ${row.y}`
                return (
                  <g key={s.id} className={`mm-leaf mm-${tone2}`} style={{ animationDelay: `${gi * 90 + si * 70}ms` }}>
                    <path d={link} className="mm-link mm-link-leaf" pathLength="1" />
                    <circle cx={x} cy={row.y} r="7" className="mm-node" />
                    {s.status === 'running' && <circle cx={x} cy={row.y} r="7" className="mm-node-pulse" />}
                    <text x={x + 13} y={row.y + 4} className="mm-leaf-label">
                      {truncate(s.text || s.agent, maxSteps > 4 ? 10 : 12)}
                    </text>
                  </g>
                )
              })}
            </g>
          )
        })}
      </svg>

      {running && (
        <div className="mm-now">
          <span className="mm-now-dot" />
          正在：{running.agent} · {running.text}
        </div>
      )}
    </div>
  )
}
