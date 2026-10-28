/** 截图：项目页的「材料与版本」与版本对比。用法：node scripts/shot_versions.mjs <chrome> <out.png> <projectId> */
import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'

const CHROME = process.argv[2]
const OUT = process.argv[3]
const PROJECT = process.argv[4] || '55'
const BASE = 'http://127.0.0.1:8000'
const PORT = 9500 + Math.floor(Math.random() * 100)

const child = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${PORT}`, '--no-first-run', '--disable-gpu', '--window-size=1440,1200', 'about:blank'], { stdio: 'ignore' })
const wait = (ms) => sleep(ms)

await wait(2500)
const target = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: 'PUT' })).json()
const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((r) => { ws.onopen = r })
let id = 0
const pending = new Map()
ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } }
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })) })
const ev = async (expr) => (await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value

await send('Page.enable')
await send('Runtime.enable')
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1200, deviceScaleFactor: 1, mobile: false })

const goto = async (url, text) => {
  await send('Page.navigate', { url: 'about:blank' })
  await wait(200)
  await send('Page.navigate', { url })
  await wait(1500)
  for (let i = 0; i < 30; i++) {
    if ((await ev('document.body.innerText'))?.includes(text)) break
    await wait(300)
  }
}

await goto(BASE, 'LawLens')
await ev(`fetch('/api/auth/login',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'admin',password:'123456'})}).then(r=>r.status)`)

await goto(`${BASE}/#/app/p/${PROJECT}`, '材料与版本')
await wait(600)
await ev(`[...document.querySelectorAll('.vg-actions button')].find(b => b.textContent.includes('对比最近两版'))?.click()`)
await wait(900)
const summary = await ev(`document.querySelector('.diff-head')?.innerText || 'no diff'`)
console.log('diff head:', summary)
const data = (await send('Page.captureScreenshot', { format: 'png' })).result.data
fs.writeFileSync(OUT, Buffer.from(data, 'base64'))
console.log('saved', path.basename(OUT))
ws.close()
spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' })
