/** 删除确认弹窗：毛玻璃 + 居中 + Esc 关闭 + 确认后真删 */
import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'

const CHROME = process.argv[2]
const OUT = process.argv[3] || 'ui-shots'
const BASE = process.env.DILIGENCE_BASE || 'http://127.0.0.1:8029'
const PORT = 9800 + Math.floor(Math.random() * 90)

const fails = []
let total = 0
const check = (cond, msg) => { total += 1; console.log((cond ? '  PASS ' : '  FAIL ') + msg); if (!cond) fails.push(msg) }

const email = `dlg${Date.now()}@example.com`
const reg = await fetch(`${BASE}/api/auth/register`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email, password: 'demo123456' }),
})
const cookie = (reg.headers.getSetCookie?.() || [reg.headers.get('set-cookie')])[0].split(';')[0]
const H = { Cookie: cookie, 'Content-Type': 'application/json' }
const proj = await (await fetch(`${BASE}/api/projects`, {
  method: 'POST', headers: H,
  body: JSON.stringify({ title: '待删除项目', subject_name: '测试主体', brief: '删除弹窗校验', board: 'all', is_demo: true }),
})).json()

const udd = path.join(os.tmpdir(), `chrome-dlg-${Date.now()}`)
const child = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${udd}`,
  '--no-first-run', '--window-size=1440,960', 'about:blank'], { stdio: 'ignore' })

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
  const waitFor = async (fn, timeout = 10000) => { const t0 = Date.now(); while (Date.now() - t0 < timeout) { try { if (await fn()) return true } catch {} await sleep(200) } return false }

  await send('Page.enable'); await send('Runtime.enable')
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 960, deviceScaleFactor: 1, mobile: false })
  await send('Page.navigate', { url: `${BASE}/login` }); await sleep(1200)
  await evaluate(`fetch('/api/auth/login',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(${JSON.stringify({ email, password: 'demo123456' })})}).then(r=>r.status)`)
  await send('Page.navigate', { url: `${BASE}/#/app` }); await sleep(1500)

  await evaluate(`document.querySelector('.link-danger').click()`)
  check(await waitFor(async () => await evaluate(`!!document.querySelector('.dlg-overlay')`)), '点删除弹出确认框')

  await sleep(320)  // 等入场动画结束再量几何
  const style = await evaluate(`(() => {
    const card = document.querySelector('.dlg-card')
    const overlay = document.querySelector('.dlg-overlay')
    const c = card.getBoundingClientRect()
    const s = getComputedStyle(card)
    const o = getComputedStyle(overlay)
    return {
      blur: s.backdropFilter || s.webkitBackdropFilter || '',
      overlayBlur: o.backdropFilter || o.webkitBackdropFilter || '',
      dx: Math.abs((c.left + c.width / 2) - innerWidth / 2),
      dy: Math.abs((c.top + c.height / 2) - innerHeight / 2),
      w: Math.round(c.width),
      title: document.querySelector('.dlg-title').innerText,
      confirm: document.querySelector('.dlg-actions .btn.danger')?.innerText || '',
    }
  })()`)
  check(String(style.blur).includes('blur'), `卡片毛玻璃：${style.blur}`)
  check(String(style.overlayBlur).includes('blur'), `遮罩毛玻璃：${style.overlayBlur}`)
  check(style.dx < 2 && style.dy < 2, `居中（偏差 x=${style.dx.toFixed(1)} y=${style.dy.toFixed(1)}）`)
  check(style.title.includes('删除'), `标题：${style.title}`)
  check(style.confirm === '删除', `确认按钮：${style.confirm}`)
  check(style.w <= 460, `卡片宽度 ${style.w}px（不铺满）`)

  const shot = await send('Page.captureScreenshot', { format: 'png' })
  fs.writeFileSync(path.join(OUT, '19-delete-dialog.png'), Buffer.from(shot.result.data, 'base64'))
  console.log('  saved 19-delete-dialog.png')

  await evaluate(`document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))`)
  check(await waitFor(async () => !(await evaluate(`!!document.querySelector('.dlg-overlay')`))), 'Esc 关闭弹窗')
  check(await evaluate(`!!document.querySelector('.link-danger')`), '取消后列表仍在')

  await evaluate(`document.querySelector('.link-danger').click()`)
  await waitFor(async () => await evaluate(`!!document.querySelector('.dlg-actions .btn.danger')`))
  await evaluate(`document.querySelector('.dlg-actions .btn.danger').click()`)
  check(await waitFor(async () => !(await evaluate(`!!document.querySelector('.dlg-overlay')`))), '确认后弹窗关闭')
  // 删除是异步的：弹窗先关、请求随后，这里轮询等它真正生效
  let goneStatus = 0
  for (let i = 0; i < 25; i++) {
    goneStatus = (await fetch(`${BASE}/api/projects/${proj.id}`, { headers: H })).status
    if (goneStatus === 404) break
    await sleep(200)
  }
  check(goneStatus === 404, `后端已删除（HTTP ${goneStatus}）`)

  ws.close()
} catch (err) {
  console.error('UI CHECK ERROR:', err.message)
  fails.push(err.message)
} finally {
  try { spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' }) } catch {}
}

console.log(fails.length ? `\n共 ${total} 项检查，${fails.length} 项失败` : `\n共 ${total} 项检查，全部通过`)
process.exit(fails.length ? 1 : 0)
