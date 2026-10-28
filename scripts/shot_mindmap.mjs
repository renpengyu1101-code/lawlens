/** 核查进度导图：跑一次真模型核查，抓运行中与完成两张图 */
import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'

const CHROME = process.argv[2]
const OUT = process.argv[3] || 'ui-shots'
const BASE = process.env.BASE || 'http://127.0.0.1:8000'
const EMAIL = process.env.EMAIL || 'admin'
const PASS = process.env.PASS || 'NMA96M3fFrgy3vPz'
const FILES = (process.env.FILES || '').split(';').filter(Boolean)
const PORT = 9960 + Math.floor(Math.random() * 30)

const udd = path.join(os.tmpdir(), `chrome-mm-${Date.now()}`)
const child = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${udd}`,
  '--no-first-run', '--window-size=1440,1100', 'about:blank'], { stdio: 'ignore' })

try {
  for (let i = 0; i < 60; i++) { try { if ((await fetch(`http://127.0.0.1:${PORT}/json/version`)).ok) break } catch {} await sleep(250) }
  const target = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: 'PUT' })).json()
  const ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej })
  let seq = 0
  const pending = new Map()
  ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } }
  const send = (m, p = {}) => new Promise((res) => { const id = ++seq; pending.set(id, res); ws.send(JSON.stringify({ id, method: m, params: p })) })
  const evaluate = async (e) => {
    const r = await send('Runtime.evaluate', { expression: e, awaitPromise: true, returnByValue: true })
    if (r.result?.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 200))
    return r.result?.result?.value
  }
  const waitFor = async (fn, timeout = 20000) => { const t0 = Date.now(); while (Date.now() - t0 < timeout) { try { if (await fn()) return true } catch {} await sleep(300) } return false }

  await send('Page.enable'); await send('DOM.enable'); await send('Runtime.enable')
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false })
  await send('Page.navigate', { url: `${BASE}/#/login` }); await sleep(1500)

  await evaluate(`(() => {
    const inputs = [...document.querySelectorAll('input')]
    const set = (el, v) => { const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; s.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })) }
    const email = inputs.find(i => /邮箱|账号|email/i.test(i.name + i.placeholder + i.type)) || inputs[0]
    const pwd = inputs.find(i => i.type === 'password')
    set(email, ${JSON.stringify(EMAIL)}); set(pwd, ${JSON.stringify(PASS)})
    ;[...document.querySelectorAll('button')].find(b => /登录/.test(b.innerText))?.click()
  })()`)
  await sleep(2500)
  console.log('hash', await evaluate('location.hash'))

  await send('Page.navigate', { url: `${BASE}/#/app` }); await sleep(1800)

  // 填问题
  await evaluate(`(() => {
    const ta = document.querySelector('.composer textarea')
    const s = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set
    s.call(ta, '核查核心资产、劳动用工与股权结构'); ta.dispatchEvent(new Event('input', { bubbles: true }))
  })()`)

  // 选文件
  const doc = await send('DOM.getDocument', { depth: -1 })
  const q = await send('DOM.querySelector', { nodeId: doc.result.root.nodeId, selector: 'input[type=file]' })
  console.log('file input', q.result?.nodeId || 'none')
  if (q.result?.nodeId) await send('DOM.setFileInputFiles', { nodeId: q.result.nodeId, files: FILES })

  await sleep(700)
  await evaluate(`[...document.querySelectorAll('button')].find(b => /开始核查/.test(b.innerText))?.click()`)

  const started = await waitFor(async () => await evaluate(`!!document.querySelector('.mindmap')`), 20000)
  console.log('导图出现', started)
  await sleep(4500)
  let shot = await send('Page.captureScreenshot', { format: 'png' })
  fs.writeFileSync(path.join(OUT, '28-mindmap-running.png'), Buffer.from(shot.result.data, 'base64'))
  console.log('saved 28-mindmap-running.png')

  const done = await waitFor(async () => await evaluate(`!!document.querySelector('.runpanel-foot')`), 180000)
  console.log('完成', done)
  await sleep(600)
  shot = await send('Page.captureScreenshot', { format: 'png' })
  fs.writeFileSync(path.join(OUT, '29-mindmap-done.png'), Buffer.from(shot.result.data, 'base64'))
  console.log('saved 29-mindmap-done.png')

  ws.close()
} catch (err) {
  console.error('失败:', err.message)
} finally {
  try { spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' }) } catch {}
}
