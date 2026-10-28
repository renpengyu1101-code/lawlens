/**
 * 账号菜单 UI 校验（右上角头像 → 二级菜单 → 修改密码 / 积分查询 / 退出登录）
 * 用法：node scripts/ui_account_check.mjs "<chrome.exe 路径>" "<截图输出目录>"
 * 前置：后端 8000、前端 dev 5173 已启动（Vite 把 /api 代理到 8000）
 */
import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'

const CHROME = process.argv[2]
const OUT = process.argv[3] || 'ui-shots'
const UI = process.env.DILIGENCE_UI_URL || 'http://127.0.0.1:5173'
const API = process.env.DILIGENCE_API_URL || 'http://127.0.0.1:8000'
const PORT = 9500 + Math.floor(Math.random() * 200)

fs.mkdirSync(OUT, { recursive: true })
const fails = []
let total = 0
const check = (cond, msg) => {
  total += 1
  console.log((cond ? '  PASS ' : '  FAIL ') + msg)
  if (!cond) fails.push(msg)
}

// ---------------------------------------------------------------- 造数据
async function seed() {
  const email = `acct${Date.now()}@example.com`
  const reg = await fetch(`${API}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password: 'demo123456' }),
  })
  if (!reg.ok) throw new Error(`注册失败 ${reg.status}`)
  const body = await reg.json()
  const userId = body.user?.id

  // 管理员给这个用户加一笔积分，制造一条流水，供「积分查询」显示
  const adminLogin = await fetch(`${API}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'admin', password: '123456' }),
  })
  if (!adminLogin.ok) throw new Error(`管理员登录失败 ${adminLogin.status}`)
  const adminCookie = (adminLogin.headers.getSetCookie?.() || [adminLogin.headers.get('set-cookie')])[0].split(';')[0]
  const added = await fetch(`${API}/api/admin/users/${userId}/credits`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Cookie: adminCookie },
    body: JSON.stringify({ delta: 25, reason: 'UI 校验：管理员调整' }),
  })
  if (!added.ok) throw new Error(`加分失败 ${added.status}: ${await added.text()}`)
  return { email, password: 'demo123456', userId }
}

// ---------------------------------------------------------------- 浏览器
const udd = path.join(os.tmpdir(), `chrome-acct-${Date.now()}`)
const child = spawn(CHROME, [
  '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${udd}`,
  '--no-first-run', '--no-default-browser-check', '--disable-gpu',
  '--window-size=1440,900', 'about:blank',
], { stdio: 'ignore' })

async function waitFor(fn, timeout = 20000, step = 250) {
  const start = Date.now()
  while (Date.now() - start < timeout) {
    try { const v = await fn(); if (v) return v } catch { /* retry */ }
    await sleep(step)
  }
  throw new Error('timeout')
}

async function ui({ email, password }) {
  await waitFor(async () => (await fetch(`http://127.0.0.1:${PORT}/json/version`)).ok)
  const target = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: 'PUT' })).json()
  const ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej })

  let seq = 0
  const pending = new Map()
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data)
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id) }
  }
  const send = (method, params = {}) => new Promise((res) => {
    const id = ++seq
    pending.set(id, res)
    ws.send(JSON.stringify({ id, method, params }))
  })

  await send('Page.enable')
  await send('Runtime.enable')
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false })

  const evaluate = async (expression) => {
    const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
    if (r.result?.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 300))
    return r.result?.result?.value
  }
  const goto = async (url, waitText) => {
    await send('Page.navigate', { url })
    await sleep(1200)
    if (waitText) await waitFor(async () => (await evaluate('document.body.innerText'))?.includes(waitText), 15000)
    await sleep(200)
  }
  const shot = async (name) => {
    const r = await send('Page.captureScreenshot', { format: 'png' })
    fs.writeFileSync(path.join(OUT, name), Buffer.from(r.result.data, 'base64'))
    console.log('  saved', name)
  }

  await goto(`${UI}/login`, '登录')
  // 同源登录，cookie 落在浏览器里（绕过表单交互，专注验证菜单本身）
  const status = await evaluate(`fetch('/api/auth/login',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(${JSON.stringify({ email, password })})}).then(r=>r.status)`)
  check(status === 200, `浏览器上下文登录成功（HTTP ${status}）`)

  await goto(`${UI}/#/app`, '工作台')
  check(await evaluate(`!!document.querySelector('.account-trigger')`), '右上角存在账号头像按钮')
  check(await evaluate(`!document.querySelector('.account-menu')`), '默认不展开二级菜单')
  check(await evaluate(`document.querySelectorAll('.userbox').length === 0`), '旧的 email+退出 组合已移除')

  // 打开菜单
  await evaluate(`document.querySelector('.account-trigger').click()`)
  await waitFor(async () => await evaluate(`!!document.querySelector('.account-menu')`))
  const menuText = await evaluate(`document.querySelector('.account-menu').innerText`)
  check(menuText.includes('积分查询'), '菜单含「积分查询」')
  check(menuText.includes('修改密码'), '菜单含「修改密码」')
  check(menuText.includes('退出登录'), '菜单含「退出登录」')
  check(menuText.includes(email), '菜单显示当前账号邮箱')
  check(await evaluate(`document.querySelectorAll('.account-menu .account-item').length === 3`), '菜单三项，无多余入口')
  const glass = await evaluate(`(() => { const s = getComputedStyle(document.querySelector('.account-menu')); return s.backdropFilter || s.webkitBackdropFilter || '' })()`)
  check(String(glass).includes('blur'), `菜单使用模糊玻璃（${glass}）`)
  await shot('12-account-menu.png')

  // 点击外部关闭
  await evaluate(`document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))`)
  await sleep(200)
  check(!(await evaluate(`!!document.querySelector('.account-menu')`)), '点击菜单外部可关闭')

  // 积分查询
  await evaluate(`document.querySelector('.account-trigger').click()`)
  await waitFor(async () => await evaluate(`!!document.querySelector('.account-menu')`))
  await evaluate(`[...document.querySelectorAll('.account-item')].find(b => b.textContent.includes('积分查询')).click()`)
  await waitFor(async () => await evaluate(`!!document.querySelector('.am-modal')`))
  await waitFor(async () => !(await evaluate(`document.body.innerText.includes('读取中')`)), 10000)
  const creditsText = await evaluate(`document.querySelector('.am-modal').innerText`)
  check(creditsText.includes('当前积分'), '积分弹窗显示「当前积分」')
  check(creditsText.includes('管理员调整'), '积分流水包含管理员加分记录')
  check(creditsText.includes('+25'), '流水显示 +25')
  const balance = await evaluate(`Number(document.querySelector('.am-balance b').textContent)`)
  check(Number.isFinite(balance) && balance >= 25, `余额读数 ${balance} ≥ 25`)
  await shot('13-account-credits.png')
  await evaluate(`document.querySelector('.am-x').click()`)
  await sleep(250)
  check(!(await evaluate(`!!document.querySelector('.am-modal')`)), '积分弹窗可关闭')

  // 修改密码：先验错密码的报错路径，不改真实密码
  await evaluate(`document.querySelector('.account-trigger').click()`)
  await waitFor(async () => await evaluate(`!!document.querySelector('.account-menu')`))
  await evaluate(`[...document.querySelectorAll('.account-item')].find(b => b.textContent.includes('修改密码')).click()`)
  await waitFor(async () => await evaluate(`!!document.querySelector('.am-modal')`))
  const pwdInputs = await evaluate(`document.querySelectorAll('.am-modal input[type=password]').length`)
  check(pwdInputs === 3, `改密弹窗有三个密码框（${pwdInputs}）`)
  await evaluate(`(() => {
    const set = (el, v) => { const s = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; s.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })) }
    const inputs = document.querySelectorAll('.am-modal input[type=password]')
    set(inputs[0], 'wrong-old-password')
    set(inputs[1], 'demo123456')
    set(inputs[2], 'demo123456')
    document.querySelector('.am-modal form button').click()
  })()`)
  // 注意：不能只断言「原密码」三字出现——那是标签文案，会假阳性；必须断言错误框内容
  await waitFor(async () => (await evaluate(`document.querySelector('.am-modal .alert.error')?.innerText || ''`)).includes('原密码不正确'), 15000)
  check(true, '原密码错误时弹出服务端报错，表单未关闭')
  await shot('14-account-password.png')
  await evaluate(`document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))`)
  await sleep(250)
  check(!(await evaluate(`!!document.querySelector('.am-modal')`)), 'Esc 关闭弹窗')

  // 退出登录
  const before = await evaluate(`location.hash`)
  await evaluate(`document.querySelector('.account-trigger').click()`)
  await waitFor(async () => await evaluate(`!!document.querySelector('.account-menu')`))
  await evaluate(`[...document.querySelectorAll('.account-item')].find(b => b.textContent.includes('退出登录')).click()`)
  await waitFor(async () => !(await evaluate(`location.hash`)).startsWith('#/app'), 15000)
  const after = await evaluate(`location.hash`)
  check(before.startsWith('#/app') && (after === '' || after === '#/'), `退出后回到落地页（${before} → ${after || '(空)'}）`)
  const landingText = await evaluate('document.body.innerText')
  check(landingText.includes('登录') || landingText.includes('注册'), '落地页重新显示登录入口')

  ws.close()
}

try {
  const seeded = await seed()
  console.log(`  造数据：用户 #${seeded.userId}，已加 25 积分`)
  await ui(seeded)
} catch (err) {
  console.error('UI CHECK ERROR:', err.message)
  fails.push(err.message)
} finally {
  try { spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' }) } catch { /* ignore */ }
}

console.log(fails.length ? `\n共 ${total} 项检查，${fails.length} 项失败` : `\n共 ${total} 项检查，全部通过`)
process.exit(fails.length ? 1 : 0)
