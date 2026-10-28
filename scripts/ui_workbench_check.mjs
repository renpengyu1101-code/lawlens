/** 工作台改版校验：改名、去入口、状态跳流程、历史项目、删除、设置移入头像菜单 */
import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'

const CHROME = process.argv[2]
const OUT = process.argv[3] || 'ui-shots'
const BASE = process.env.DILIGENCE_BASE || 'http://127.0.0.1:8028'
const SAMPLES = path.resolve('samples/虚构材料-澜川精密-2026-10')
const PORT = 9750 + Math.floor(Math.random() * 100)

const fails = []
let total = 0
const check = (cond, msg) => { total += 1; console.log((cond ? '  PASS ' : '  FAIL ') + msg); if (!cond) fails.push(msg) }

const email = `wb${Date.now()}@example.com`
const reg = await fetch(`${BASE}/api/auth/register`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email, password: 'demo123456' }),
})
const cookie = (reg.headers.getSetCookie?.() || [reg.headers.get('set-cookie')])[0].split(';')[0]
const H = { Cookie: cookie }
const proj = await (await fetch(`${BASE}/api/projects`, {
  method: 'POST', headers: { ...H, 'Content-Type': 'application/json' },
  body: JSON.stringify({ title: '工作台改版校验', subject_name: '澜川精密科技有限公司', brief: '核查资产', board: 'all', is_demo: true }),
})).json()
const form = new FormData()
for (const f of fs.readdirSync(SAMPLES).filter((n) => n.startsWith('资产') && n.endsWith('.docx'))) {
  form.append('files', new Blob([fs.readFileSync(path.join(SAMPLES, f))]), f)
}
await fetch(`${BASE}/api/projects/${proj.id}/documents`, { method: 'POST', headers: H, body: form })
await fetch(`${BASE}/api/projects/${proj.id}/run`, { method: 'POST', headers: H })
for (let i = 0; i < 40; i++) {
  await sleep(400)
  const d = await (await fetch(`${BASE}/api/projects/${proj.id}`, { headers: H })).json()
  if (['pending_review', 'done', 'failed', 'awaiting_materials'].includes(d.project.status)) break
}

const udd = path.join(os.tmpdir(), `chrome-wb-${Date.now()}`)
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
  const waitFor = async (fn, timeout = 12000) => { const t0 = Date.now(); while (Date.now() - t0 < timeout) { try { if (await fn()) return true } catch {} await sleep(250) } return false }

  await send('Page.enable'); await send('Runtime.enable')
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 960, deviceScaleFactor: 1, mobile: false })
  await send('Page.navigate', { url: `${BASE}/login` }); await sleep(1200)
  await evaluate(`fetch('/api/auth/login',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(${JSON.stringify({ email, password: 'demo123456' })})}).then(r=>r.status)`)
  await send('Page.navigate', { url: `${BASE}/#/app` }); await sleep(1600)

  const nav = await evaluate(`[...document.querySelectorAll('.nav a')].map(a=>a.textContent).join('|')`)
  check(nav.includes('透镜工作台'), `导航含「透镜工作台」：${nav}`)
  check(nav.includes('历史项目'), '导航含「历史项目」')
  check(!nav.includes('新建核查'), '导航已移除「新建核查」')
  check(!nav.includes('设置'), '导航已移除「设置」')

  check((await evaluate(`document.querySelector('h1').innerText`)) === '透镜工作台', '标题为「透镜工作台」')
  check((await evaluate(`document.body.innerText`)).includes('把你的问题，交给透镜。'), '副标题已替换')
  const ph = await evaluate(`document.querySelector('.composer textarea')?.getAttribute('placeholder') || ''`)
  check(ph.startsWith('例：') && !ph.includes('，以及'), `对话框提示只保留一句：${ph}`)
  check(!(await evaluate(`document.body.innerText.includes('高级设置')`)), '「高级设置」入口已删除')

  check(await evaluate(`!!document.querySelector('.badge-link')`), '状态徽章可点')
  check(await evaluate(`!!document.querySelector('.link-danger')`), '最近项目有删除按钮')

  // 点状态 → 跳到项目页并滚到工作流程
  await evaluate(`document.querySelector('.badge-link').click()`)
  await waitFor(async () => (await evaluate('location.hash')).startsWith('#/app/p/'))
  const inView = await waitFor(async () => await evaluate(`(() => {
    const el = document.querySelector('#workflow'); if (!el) return false
    const r = el.getBoundingClientRect(); return r.top >= -40 && r.top < window.innerHeight
  })()`), 8000)
  check(inView, '点击状态后工作流程区块滚入视口')
  check((await evaluate(`document.querySelector('#workflow h2')?.innerText || ''`)).includes('工作流程'), '项目页有「工作流程」区块')

  const r = await send('Page.captureScreenshot', { format: 'png' })
  fs.writeFileSync(path.join(OUT, '18-workflow-jump.png'), Buffer.from(r.result.data, 'base64'))
  console.log('  saved 18-workflow-jump.png')

  // 头像菜单里有「设置」
  await send('Page.navigate', { url: `${BASE}/#/app` }); await sleep(1200)
  await evaluate(`document.querySelector('.account-trigger').click()`)
  await waitFor(async () => await evaluate(`!!document.querySelector('.account-menu')`))
  const menu = await evaluate(`document.querySelector('.account-menu').innerText`)
  check(menu.includes('设置'), '头像下拉菜单含「设置」')

  // 历史项目页
  await send('Page.navigate', { url: `${BASE}/#/app/history` }); await sleep(1200)
  check((await evaluate(`document.querySelector('h1').innerText`)) === '历史项目', '历史项目页可访问')
  check(await evaluate(`!!document.querySelector('.table tbody tr')`), '历史项目列出记录')

  // 删除（headless 里 confirm 默认 false，先覆盖成 true）
  await send('Page.navigate', { url: `${BASE}/#/app` }); await sleep(1200)
  await evaluate(`window.confirm = () => true`)
  const before = await evaluate(`document.querySelectorAll('.table tbody tr').length`)
  await evaluate(`document.querySelector('.link-danger').click()`)
  await waitFor(async () => (await evaluate(`document.querySelectorAll('.table tbody tr').length`)) < before, 6000)
  check((await evaluate(`document.querySelectorAll('.table tbody tr').length`)) < before, '删除后列表移除该行')
  const gone = await fetch(`${BASE}/api/projects/${proj.id}`, { headers: H })
  check(gone.status === 404, `后端已删除（HTTP ${gone.status}）`)

  ws.close()
} catch (err) {
  console.error('UI CHECK ERROR:', err.message)
  fails.push(err.message)
} finally {
  try { spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' }) } catch {}
}

console.log(fails.length ? `\n共 ${total} 项检查，${fails.length} 项失败` : `\n共 ${total} 项检查，全部通过`)
process.exit(fails.length ? 1 : 0)
