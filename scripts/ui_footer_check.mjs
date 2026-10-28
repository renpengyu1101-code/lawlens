/** 页脚校验：四组链接、外链新窗口、内部链接可用 */
import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'

const CHROME = process.argv[2]
const OUT = process.argv[3] || 'ui-shots'
const BASE = process.env.DILIGENCE_BASE || 'http://127.0.0.1:8031'
const PORT = 9900 + Math.floor(Math.random() * 60)

const fails = []
let total = 0
const check = (cond, msg) => { total += 1; console.log((cond ? '  PASS ' : '  FAIL ') + msg); if (!cond) fails.push(msg) }

const email = `ft${Date.now()}@example.com`
await fetch(`${BASE}/api/auth/register`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email, password: 'demo123456' }),
})

const udd = path.join(os.tmpdir(), `chrome-ft-${Date.now()}`)
const child = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${udd}`,
  '--no-first-run', '--window-size=1440,1000', 'about:blank'], { stdio: 'ignore' })

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
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })
  await send('Page.navigate', { url: `${BASE}/login` }); await sleep(1100)
  await evaluate(`fetch('/api/auth/login',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(${JSON.stringify({ email, password: 'demo123456' })})}).then(r=>r.status)`)
  await send('Page.navigate', { url: `${BASE}/#/app` }); await sleep(1400)

  check(await evaluate(`!!document.querySelector('footer.site-footer')`), '页面底部有页脚')
  const groups = await evaluate(`[...document.querySelectorAll('.footer-col h4')].map(h=>h.innerText).join('|')`)
  check(groups.includes('监管与规则') && groups.includes('尽调数据源') && groups.includes('披露与行业'),
    `分组：${groups}`)

  const ext = await evaluate(`[...document.querySelectorAll('.footer-col a')].filter(a=>a.target==='_blank').length`)
  check(ext >= 10, `外链 ${ext} 条，全部新窗口打开`)
  check(await evaluate(`[...document.querySelectorAll('.footer-col a[target="_blank"]')].every(a=>a.rel.includes('noopener'))`),
    '外链均带 rel=noopener')

  const hrefs = await evaluate(`[...document.querySelectorAll('.footer-col a[target="_blank"]')].map(a=>a.href)`)
  check(hrefs.every((h) => h.startsWith('http')), '外链都是绝对地址')
  check(hrefs.some((h) => h.includes('hkex.com.hk')), '含港交所上市规则')
  check(hrefs.some((h) => h.includes('gsxt.gov.cn')), '含国家企业信用信息公示系统')

  const internal = await evaluate(`[...document.querySelectorAll('.footer-col a:not([target="_blank"])')].length`)
  check(internal === 0, `页脚不再有站内链接（${internal} 条）`)
  check(!groups.includes('本系统'), '「本系统」分组已移除')
  check(!(await evaluate(`document.querySelector('footer').innerText.includes('LawLens')`)), '页脚不再出现 LawLens')
  check((await evaluate(`document.querySelector('footer').innerText`)).includes('不构成法律意见'), '页脚保留免责说明')

  await send('Page.navigate', { url: `${BASE}/#/app/history` }); await sleep(1200)
  check(await evaluate(`!!document.querySelector('footer.site-footer')`), '历史项目页同样有页脚')

  const shot = await send('Page.captureScreenshot', { format: 'png' })
  fs.writeFileSync(path.join(OUT, '21-footer.png'), Buffer.from(shot.result.data, 'base64'))
  console.log('  saved 21-footer.png')

  ws.close()
} catch (err) {
  console.error('UI CHECK ERROR:', err.message)
  fails.push(err.message)
} finally {
  try { spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' }) } catch {}
}

console.log(fails.length ? `\n共 ${total} 项检查，${fails.length} 项失败` : `\n共 ${total} 项检查，全部通过`)
process.exit(fails.length ? 1 : 0)
