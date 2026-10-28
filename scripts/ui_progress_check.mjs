/**
 * 核查进度 UI 校验：点「开始核查」后应出现动态进度，逐步显示当前维度与正在做的事。
 * 用法：node scripts/ui_progress_check.mjs "<chrome.exe 路径>" "<输出目录>"
 */
import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { setTimeout as sleep } from 'node:timers/promises'

const CHROME = process.argv[2]
const OUT = process.argv[3] || 'ui-shots'
const UI = process.env.DILIGENCE_UI_URL || 'http://127.0.0.1:5173'
const API = process.env.DILIGENCE_API_URL || 'http://127.0.0.1:8000'
const HERE = path.dirname(fileURLToPath(import.meta.url))
const SAMPLES = path.resolve(HERE, '..', 'samples', '虚构材料-澜川精密-2026-10')
const PORT = 9600 + Math.floor(Math.random() * 200)

fs.mkdirSync(OUT, { recursive: true })
const fails = []
let total = 0
const check = (cond, msg) => {
  total += 1
  console.log((cond ? '  PASS ' : '  FAIL ') + msg)
  if (!cond) fails.push(msg)
}

const email = `prog${Date.now()}@example.com`
const password = 'demo123456'
const reg = await fetch(`${API}/api/auth/register`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email, password }),
})
if (!reg.ok) throw new Error(`注册失败 ${reg.status}`)

const items = fs.readdirSync(SAMPLES).filter((f) => f.endsWith('.docx'))

const udd = path.join(os.tmpdir(), `chrome-prog-${Date.now()}`)
const child = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${udd}`,
  '--no-first-run', '--no-default-browser-check', '--window-size=1440,1000', 'about:blank'], { stdio: 'ignore' })

const waitFor = async (fn, timeout = 30000, step = 250) => {
  const t0 = Date.now()
  while (Date.now() - t0 < timeout) { try { const v = await fn(); if (v) return v } catch { /* retry */ } await sleep(step) }
  throw new Error('timeout')
}

try {
  await waitFor(async () => (await fetch(`http://127.0.0.1:${PORT}/json/version`)).ok)
  const target = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: 'PUT' })).json()
  const ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej })
  let seq = 0
  const pending = new Map()
  ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } }
  const send = (method, params = {}) => new Promise((res) => { const id = ++seq; pending.set(id, res); ws.send(JSON.stringify({ id, method, params })) })
  const evaluate = async (expression) => {
    const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
    if (r.result?.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 400))
    return r.result?.result?.value
  }
  const shot = async (name) => {
    const r = await send('Page.captureScreenshot', { format: 'png' })
    fs.writeFileSync(path.join(OUT, name), Buffer.from(r.result.data, 'base64'))
    console.log('  saved', name)
  }

  await send('Page.enable'); await send('Runtime.enable'); await send('DOM.enable')
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })

  await send('Page.navigate', { url: `${UI}/login` }); await sleep(1200)
  const status = await evaluate(`fetch('/api/auth/login',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(${JSON.stringify({ email, password })})}).then(r=>r.status)`)
  check(status === 200, `登录（HTTP ${status}）`)

  await send('Page.navigate', { url: `${UI}/#/app` })
  await waitFor(async () => (await evaluate('document.body.innerText'))?.includes('工作台'))
  await sleep(400)

  check(!(await evaluate(`!!document.querySelector('.composer select')`)), '工作台不再有「知识库」下拉框')
  check((await evaluate('document.body.innerText')).includes('每次核查固定覆盖三个维度'), '工作台写明固定三维度')

  // 填问题 + 选材料
  await evaluate(`(() => {
    const ta = document.querySelector('.composer textarea')
    const s = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set
    s.call(ta, '核查澜川精密的不动产、土地、租赁、资质，劳动用工，以及股权与对赌安排')
    ta.dispatchEvent(new Event('input', { bubbles: true }))
    return true
  })()`)
  const input = await send('Runtime.evaluate', { expression: `document.querySelector('.composer input[type=file]')` })
  await send('DOM.setFileInputFiles', { objectId: input.result.result.objectId, files: items.map((n) => path.join(SAMPLES, n)) })
  await waitFor(async () => await evaluate(`document.querySelectorAll('.attachment-list li').length >= ${items.length}`))
  check(true, `附上 ${items.length} 份材料`)

  await evaluate(`document.querySelector('.composer .send').click()`)
  await waitFor(async () => await evaluate(`!!document.querySelector('.runpanel')`), 30000)
  check(true, '点「开始核查」后出现进度面板')
  check((await evaluate(`document.querySelector('.runpanel-title').innerText`)) === '三维度全面核查', '面板标题为「三维度全面核查」')

  const samples = []
  let midShot = false
  let finalShot = false
  for (let i = 0; i < 240; i++) {
    const snap = await evaluate(`(() => {
      const p = document.querySelector('.runpanel')
      if (!p) return null
      const now = document.querySelector('.run-now')
      return {
        meta: (document.querySelector('.runpanel-meta') || {}).innerText || '',
        now: now ? now.innerText : '',
        steps: document.querySelectorAll('.runsteps .runstep').length,
        spinners: document.querySelectorAll('.rs-icon.spinner').length,
        chips: [...document.querySelectorAll('.board-chip')].map((c) => c.className.replace('board-chip', '').trim()),
        finished: !!document.querySelector('.runpanel-foot'),
        verdict: (document.querySelector('.runpanel-foot') || {}).innerText || '',
      }
    })()`)
    if (snap) {
      samples.push(snap)
      if (!midShot && snap.steps >= 5 && !snap.finished) { await shot('15-check-progress.png'); midShot = true }
      if (snap.finished) { if (!finalShot) { await shot('16-check-done.png'); finalShot = true } break }
    }
    await sleep(300)
  }

  const distinctNow = [...new Set(samples.map((s) => s.now).filter(Boolean))]
  const withSpinner = samples.filter((s) => s.spinners > 0).length
  const maxSteps = Math.max(...samples.map((s) => s.steps))
  const last = samples[samples.length - 1] || {}

  check(maxSteps >= 12, `步骤逐步出现（最多 ${maxSteps} 步）`)
  check(distinctNow.length >= 3, `「正在做」的文案会变（出现 ${distinctNow.length} 种）`)
  check(withSpinner >= 2, `进度中有旋转中的步骤（${withSpinner} 次采样命中）`)
  check(samples.some((s) => s.chips.some((c) => c === 'active')), '维度标签会显示「进行中」')
  check(last.finished, '进度最终进入完成态')
  check(last.chips.length === 3 && last.chips.every((c) => c === 'done'), `三个维度都跑完（${last.chips.join('/')}）`)
  check(last.verdict.includes('完成'), `完成提示：${last.verdict.replace(/\s+/g, ' ').slice(0, 40)}`)

  // 进入结果页，确认风险清单来自三维度
  await evaluate(`[...document.querySelectorAll('.runpanel-foot button')].pop().click()`)
  await waitFor(async () => (await evaluate('document.body.innerText')).includes('风险清单'), 20000)
  const detail = await evaluate('document.body.innerText')
  check(detail.includes('三维度全面核查'), '结果页标注「三维度全面核查」')
  const codes = await evaluate(`[...document.querySelectorAll('.badge')].map(b=>b.textContent)`)

  ws.close()
} catch (err) {
  console.error('UI CHECK ERROR:', err.message)
  fails.push(err.message)
} finally {
  try { spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' }) } catch { /* ignore */ }
}

console.log(fails.length ? `\n共 ${total} 项检查，${fails.length} 项失败` : `\n共 ${total} 项检查，全部通过`)
process.exit(fails.length ? 1 : 0)
