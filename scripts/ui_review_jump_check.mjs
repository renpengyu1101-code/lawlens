/** 「待律师复核」徽章可点：点击后应跳到项目页并定位到复核区块 */
import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'

const CHROME = process.argv[2]
const OUT = process.argv[3] || 'ui-shots'
const BASE = process.env.DILIGENCE_BASE || 'http://127.0.0.1:8027'
const SAMPLES = path.resolve('samples/虚构材料-澜川精密-2026-10')
const PORT = 9700 + Math.floor(Math.random() * 100)

const fails = []
let total = 0
const check = (cond, msg) => { total += 1; console.log((cond ? '  PASS ' : '  FAIL ') + msg); if (!cond) fails.push(msg) }

const email = `rv${Date.now()}@example.com`
const c = await fetch(`${BASE}/api/auth/register`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email, password: 'demo123456' }),
})
const cookie = (c.headers.getSetCookie?.() || [c.headers.get('set-cookie')])[0].split(';')[0]
const H = { Cookie: cookie }

const proj = await (await fetch(`${BASE}/api/projects`, {
  method: 'POST', headers: { ...H, 'Content-Type': 'application/json' },
  body: JSON.stringify({ title: '复核跳转校验', subject_name: '', brief: '核查资产', board: 'all', is_demo: true }),
})).json()

const files = fs.readdirSync(SAMPLES).filter((f) => f.startsWith('资产') && f.endsWith('.docx'))
const form = new FormData()
for (const f of files) form.append('files', new Blob([fs.readFileSync(path.join(SAMPLES, f))]), f)
await fetch(`${BASE}/api/projects/${proj.id}/documents`, { method: 'POST', headers: H, body: form })
await fetch(`${BASE}/api/projects/${proj.id}/run`, { method: 'POST', headers: H })
for (let i = 0; i < 40; i++) {
  await sleep(500)
  const d = await (await fetch(`${BASE}/api/projects/${proj.id}`, { headers: H })).json()
  if (['pending_review', 'done', 'failed', 'awaiting_materials'].includes(d.project.status)) break
}

const udd = path.join(os.tmpdir(), `chrome-rv-${Date.now()}`)
const child = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${udd}`,
  '--no-first-run', '--window-size=1440,900', 'about:blank'], { stdio: 'ignore' })

try {
  for (let i = 0; i < 60; i++) { try { if ((await fetch(`http://127.0.0.1:${PORT}/json/version`)).ok) break } catch {} await sleep(250) }
  const target = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: 'PUT' })).json()
  const ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej })
  let seq = 0
  const pending = new Map()
  ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } }
  const send = (method, params = {}) => new Promise((res) => { const id = ++seq; pending.set(id, res); ws.send(JSON.stringify({ id, method, params })) })
  const evaluate = async (expression) => {
    const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
    if (r.result?.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 300))
    return r.result?.result?.value
  }
  const waitFor = async (fn, timeout = 15000) => { const t0 = Date.now(); while (Date.now() - t0 < timeout) { try { if (await fn()) return true } catch {} await sleep(250) } return false }

  await send('Page.enable'); await send('Runtime.enable')
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false })
  await send('Page.navigate', { url: `${BASE}/login` }); await sleep(1200)
  await evaluate(`fetch('/api/auth/login',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(${JSON.stringify({ email, password: 'demo123456' })})}).then(r=>r.status)`)
  await send('Page.navigate', { url: `${BASE}/#/app` }); await sleep(1500)

  const hasLink = await evaluate(`!!document.querySelector('a.badge-link')`)
  check(hasLink, '工作台「待律师复核」徽章是链接')
  const label = await evaluate(`document.querySelector('a.badge-link')?.innerText || ''`)
  check(label.includes('待律师复核'), `徽章文案：${label}`)

  await evaluate(`document.querySelector('a.badge-link').click()`)
  await waitFor(async () => (await evaluate('location.hash')).startsWith('#/app/p/'))
  check((await evaluate('location.hash')).startsWith('#/app/p/'), '点击后跳到项目页')

  const inView = await waitFor(async () => await evaluate(`(() => {
    const el = document.querySelector('#review')
    if (!el) return false
    const r = el.getBoundingClientRect()
    return r.top >= -40 && r.top < window.innerHeight
  })()`), 8000)
  check(inView, '复核区块已滚入视口')
  check(await evaluate(`!!document.querySelector('#review')`), '页面存在 #review 锚点')

  const r = await send('Page.captureScreenshot', { format: 'png' })
  fs.writeFileSync(path.join(OUT, process.env.SHOT_NAME || '17-review-jump.png'), Buffer.from(r.result.data, 'base64'))
  console.log('  saved', process.env.SHOT_NAME || '17-review-jump.png')
  ws.close()
} catch (err) {
  console.error('UI CHECK ERROR:', err.message)
  fails.push(err.message)
} finally {
  try { spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' }) } catch {}
}

console.log(fails.length ? `\n共 ${total} 项检查，${fails.length} 项失败` : `\n共 ${total} 项检查，全部通过`)
process.exit(fails.length ? 1 : 0)
