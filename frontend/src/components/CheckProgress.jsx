import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import MindMap from './MindMap'

const TERMINAL = new Set(['done', 'pending_review', 'failed', 'awaiting_materials'])

const STEP_TONE = {
  running: 'run',
  ok: 'ok',
  warn: 'warn',
  skip: 'skip',
  fail: 'fail',
}

function StepIcon({ status }) {
  if (status === 'running') return <span className="rs-icon spinner" aria-label="进行中" />
  return <span className={`rs-icon ${STEP_TONE[status] || ''}`} aria-hidden="true">{
    status === 'ok' ? '✓' : status === 'warn' ? '!' : status === 'skip' ? '–' : status === 'fail' ? '✕' : '·'
  }</span>
}

/**
 * 核查进度：轮询后端步骤，边跑边显示「当前维度 + 正在做什么」。
 * 后端每一步先写 running 再写终态，所以这里能看出是哪一步正在工作。
 */
export default function CheckProgress({ projectId, onOpen, onReset, onSettled }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const listRef = useRef(null)
  const startedAt = useRef(Date.now())
  const settled = useRef(false)

  useEffect(() => {
    let alive = true
    let poll = null
    const tick = async () => {
      try {
        const d = await api.progress(projectId)
        if (!alive) return
        setData(d)
        setError('')
        if (TERMINAL.has(d.status) && poll) {
          clearInterval(poll)
          if (!settled.current) { settled.current = true; onSettled?.() }
        }
      } catch (err) {
        if (alive) setError(err.message)
      }
    }
    tick()
    poll = setInterval(tick, 700)
    const clock = setInterval(() => setElapsed(Math.round((Date.now() - startedAt.current) / 1000)), 500)
    return () => {
      alive = false
      clearInterval(poll)
      clearInterval(clock)
    }
  }, [projectId])

  const count = data?.steps?.length || 0
  useEffect(() => {
    const el = listRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [count])

  const steps = data?.steps || []
  const running = data?.current || null
  const finished = data ? TERMINAL.has(data.status) : false

  const verdict = finished
    ? data.status === 'failed' ? '执行失败'
      : data.status === 'awaiting_materials' ? '材料不全，已暂停'
        : `完成：${data.findings ?? 0} 条风险`
    : ''

  return (
    <section className="runpanel">
      <div className="runpanel-head">
        <div>
          <span className="runpanel-title">三维度全面核查</span>
          <span className="runpanel-sub">
            {finished ? verdict : (running ? `正在核查：${running.board || '汇总'}` : '准备中…')}
          </span>
        </div>
        <span className="runpanel-meta">{data ? `已完成 ${data.done} 步` : '—'} · {elapsed}s</span>
      </div>

      {steps.length > 0 && <MindMap steps={steps} running={running} />}


      <ol className="runsteps" ref={listRef}>
        {steps.map((s) => (
          <li key={s.id} className={`runstep ${STEP_TONE[s.status] || ''}`}>
            <StepIcon status={s.status} />
            <span className="rs-agent">{s.agent}</span>
            <span className="rs-text">
              {s.board ? <span className="rs-board">{s.board}</span> : null}
              {s.text}
            </span>
          </li>
        ))}
        {!steps.length && <li className="runstep"><span className="rs-agent">等待流水线启动…</span></li>}
      </ol>

      {error && <div className="alert error">{error}</div>}

      {finished && (
        <div className="runpanel-foot">
          <span className={`badge ${data.status === 'failed' ? 'red' : data.status === 'awaiting_materials' ? 'amber' : 'green'}`}>
            {verdict}
          </span>
          <div className="actions">
            {onReset && <button className="btn ghost sm" onClick={() => onReset()}>再核查一次</button>}
            <button className="btn primary sm" onClick={() => onOpen?.()}>
              {data.status === 'awaiting_materials' ? '去补材料' : '查看结果'}
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
