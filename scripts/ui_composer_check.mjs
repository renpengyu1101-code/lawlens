/** 对话框区域精简校验：只留一句提示，删掉维度条与港股说明 */
import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'

const CHROME = process.argv[2]
const OUT = process.argv[3] || 'ui-shots'
const BASE = process.env.DILIGENCE_BASE || 'http://127.0.0.1:8030'
const PORT = 9850 + Math.floor(Math.random() * 90)

const fails = []
let total = 0
const check = (cond, msg) => { total += 1; console.log((cond ? '  PASS ' : '  FAIL ') + msg); if (!cond) fails.push(msg) }

const email = `cp${Date.now()}@example.com`
const reg = await fetch(`${BASE}/api/auth/register`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email, password: 'demo123456' }),
})
const cookie = (reg.headers.getSetCookie?.() || [reg.headers.get('set-cookie')])[0].split(';')[0]

const udd = path.join(os.tmpdir(), `chrome-cp-${Date.now()}`)
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
    if (r.result?.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 260))
    return r.result?.result?.value
  }

  await send('Page.enable'); await send('Runtime.enable')
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false })
  await send('Page.navigate', { url: `${BASE}/login` }); await sleep(1100)
  await evaluate(`fetch('/api/auth/login',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(${JSON.stringify({ email, password: 'demo123456' })})}).then(r=>r.status)`)
  await send('Page.navigate', { url: `${BASE}/#/app` }); await sleep(1400)

  const ph = await evaluate(`document.querySelector('.composer textarea').getAttribute('placeholder')`)
  check(ph === '例：我想评估一下我们公司港股上市可能性', `提示文案：${ph}`)
  check(!(await evaluate(`!!document.querySelector('.composer-dims')`)), '三维度标签行已移除')
  check(!(await evaluate(`!!document.querySelector('.composer-note')`)), '港股材料说明段已移除')
  check(!(await evaluate(`document.body.innerText.includes('每次核查固定覆盖三个维度')`)), '页面不再出现「三个维度」说明')
  const h = await evaluate(`Math.round(document.querySelector('.composer').getBoundingClientRect().height)`)
  check(h < 280, `对话框高度 ${h}px（精简后更矮）`)

  const shot = await send('Page.captureScreenshot', { format: 'png', clip: { x: 170, y: 170, width: 1100, height: 330, scale: 1.4 } })
  fs.writeFileSync(path.join(OUT, '20-composer.png'), Buffer.from(shot.result.data, 'base64'))
  console.log('  saved 20-composer.png')

  ws.close()
} catch (err) {
  console.error('UI CHECK ERROR:', err.message)
  fails.push(err.message)
} finally {
  try { spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' }) } catch {}
}

console.log(fails.length ? `\n共 ${total} 项检查，${fails.length} 项失败` : `\n共 ${total} 项检查，全部通过`)
process.exit(fails.length ? 1 : 0)
