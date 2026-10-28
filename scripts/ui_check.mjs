/**
 * 无头浏览器 UI 校验（自包含）：
 * 先用 API 造数据（注册→建项目→上传→跑流水线），再用 Chrome 逐页断言并截图。
 * 用法：node scripts/ui_check.mjs "<chrome.exe 路径>" "<输出目录>"
 */
import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'

const CHROME = process.argv[2]
const OUT = process.argv[3] || 'ui-shots'
const BASE = process.env.DILIGENCE_TEST_BASE_URL || 'http://127.0.0.1:8000'
const PORT = 9300 + Math.floor(Math.random() * 200)
const SAMPLES = path.resolve('samples/虚构测试样本')

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
  const email = `ui${Date.now()}@example.com`
  const reg = await fetch(`${BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password: 'demo123456' }),
  })
  if (!reg.ok) throw new Error(`注册失败 ${reg.status}`)
  const cookie = (reg.headers.getSetCookie?.() || [reg.headers.get('set-cookie')])[0].split(';')[0]
  const auth = { Cookie: cookie }

  const proj = await (await fetch(`${BASE}/api/projects`, {
    method: 'POST',
    headers: { ...auth, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: '云澜智造 港股IPO 资产核查（UI 自动校验）',
      subject_name: '云澜智造科技有限公司',
      brief: '核查核心资产权属与经营基础',
      board: 'asset',
      is_demo: true,
    }),
  })).json()

  const files = fs.readdirSync(SAMPLES).filter((f) => f.endsWith('.docx'))
  const form = new FormData()
  for (const f of files) {
    form.append('files', new Blob([fs.readFileSync(path.join(SAMPLES, f))]), f)
  }
  const up = await fetch(`${BASE}/api/projects/${proj.id}/documents`, { method: 'POST', headers: auth, body: form })
  if (!up.ok) throw new Error(`上传失败 ${up.status}: ${await up.text()}`)

  await fetch(`${BASE}/api/projects/${proj.id}/run`, { method: 'POST', headers: auth })
  for (let i = 0; i < 40; i++) {
    await sleep(500)
    const d = await (await fetch(`${BASE}/api/projects/${proj.id}`, { headers: auth })).json()
    if (['done', 'pending_review', 'failed', 'awaiting_materials'].includes(d.project.status)) {
      return { email, projectId: proj.id, status: d.project.status, findings: d.findings.length }
    }
  }
  throw new Error('流水线超时')
}

// ---------------------------------------------------------------- 浏览器
const udd = path.join(os.tmpdir(), `chrome-ui-${Date.now()}`)
const child = spawn(CHROME, [
  '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${udd}`,
  '--no-first-run', '--no-default-browser-check', '--disable-gpu',
  '--window-size=1440,1100', 'about:blank',
], { stdio: 'ignore' })

async function waitFor(fn, timeout = 20000, step = 300) {
  const start = Date.now()
  while (Date.now() - start < timeout) {
    try { const v = await fn(); if (v) return v } catch { /* retry */ }
    await sleep(step)
  }
  throw new Error('timeout')
}

async function ui({ email, projectId }) {
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
  await send('Network.enable')
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false })
  // 注意：不覆盖 prefers-reduced-motion —— 本机默认是 reduce，正好用来验证"系统关掉动效时透镜仍然运动"

  const evaluate = async (expression) => {
    const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
    if (r.result?.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 300))
    return r.result?.result?.value
  }

  const goto = async (url, waitText) => {
    await send('Page.navigate', { url: 'about:blank' })
    await sleep(250)
    await send('Page.navigate', { url })
    await sleep(1400)
    if (waitText) {
      try {
        await waitFor(async () => (await evaluate('document.body.innerText'))?.includes(waitText), 15000)
      } catch (err) {
        console.log('  DEBUG url:', await evaluate('location.href'))
        console.log('  DEBUG text:', String(await evaluate('document.body.innerText')).slice(0, 240))
        throw err
      }
    }
    await sleep(300)
  }

  const shot = async (name) => {
    const r = await send('Page.captureScreenshot', { format: 'png' })
    fs.writeFileSync(path.join(OUT, name), Buffer.from(r.result.data, 'base64'))
    console.log('  saved', name)
  }

  // 1) 访客：落地页（品牌、一句话、居中的登录/注册；三枚透镜放大）
  await goto(BASE, '上市准备中的法律风险')
  const landing = await evaluate('document.body.innerText')
  check(landing.includes('LawLens') && landing.includes('登录') && landing.includes('注册'), '访客页：品牌 + 登录/注册')
  const banned = ['衡鉴', '法律透镜', '劳动用工', '投资退出', '六步', '三个痛点'].filter((w) => landing.includes(w))
  check(banned.length === 0, `访客页无旧名/板块/流程${banned.length ? '，泄露：' + banned.join('/') : ''}`)
  const copyCount = await evaluate(`document.querySelectorAll('.lens-copy').length`)
  check(copyCount === 8, `八枚透镜内容副本存在（${copyCount}）`)
  const ringCount = await evaluate(`document.querySelectorAll('.lens-ring').length`)
  check(ringCount === 8, `八枚镜圈存在（${ringCount}）`)
  const lineCount = await evaluate(`document.querySelectorAll('.lens-text.dim span').length`)
  check(lineCount >= 20, `底部风险文字 ${lineCount} 条`)

  const readCopy = `(() => { const c = document.querySelector('.lens-copy'); const i = document.querySelector('.lens-inner'); return { left: c.style.left, top: c.style.top, scale: i.style.transform } })()`
  const c1 = await evaluate(readCopy)
  const scaleVal = parseFloat((String(c1.scale).match(/scale\(([\d.]+)\)/) || [])[1])
  check(scaleVal > 1.1, `透镜内内容被放大（${c1.scale}）`)

  // 连续采样 1.2 秒，累计路径长度：避免恰好采样在速度拐点造成误判
  let prev = c1
  let travelled = 0
  let minStep = Infinity
  for (let i = 0; i < 6; i++) {
    await sleep(200)
    const cur = await evaluate(readCopy)
    const step = Math.abs(parseFloat(cur.left) - parseFloat(prev.left)) + Math.abs(parseFloat(cur.top) - parseFloat(prev.top))
    travelled += step
    minStep = Math.min(minStep, step)
    prev = cur
  }
  check(travelled >= 20, `1.2 秒累计位移 ${travelled.toFixed(1)}px（阈值 20px）`)
  check(minStep >= 1, `最慢的 0.2 秒也有 ${minStep.toFixed(1)}px 位移（不会停住）`)

  const fullViewport = await evaluate(`(() => { const el = document.querySelector('.lens-scene'); const r = el.getBoundingClientRect(); return getComputedStyle(el).position === 'fixed' && Math.abs(r.width - innerWidth) < 2 && Math.abs(r.height - innerHeight) < 2 })()`)
  check(fullViewport, '透镜层覆盖整个视口（活动范围为全网页）')
  const centered = await evaluate(`(() => { const box = document.querySelector('.home-login') || document.querySelector('.auth-actions > *'); const r = box.getBoundingClientRect(); return Math.abs(r.left + r.width / 2 - innerWidth / 2) < 8 && Math.abs(r.top + r.height / 2 - innerHeight / 2) < 8 })()`)
  check(centered, '登录卡片位于视口中央')
  const inlineForm = await evaluate(`document.querySelectorAll('.home-login input').length`)
  check(inlineForm === 2, `首页内嵌登录表单（${inlineForm} 个输入框）`)
  await shot('01-landing.png')

  // 2) 直接在首页表单登录（不跳转登录页）
  const filled = await evaluate(`(() => {
    const set = (el, v) => { const s = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; s.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })) }
    const inputs = document.querySelectorAll('.home-login input')
    if (inputs.length < 2) return false
    set(inputs[0], ${JSON.stringify(email)})
    set(inputs[1], 'demo123456')
    document.querySelector('.home-login button').click()
    return true
  })()`)
  check(filled, '在首页表单填入账号密码并提交')
  await waitFor(async () => (await evaluate('location.hash'))?.startsWith('#/app'), 15000)
  await waitFor(async () => (await evaluate('document.body.innerText'))?.includes('工作台'), 15000)
  check(true, '登录后直接进入工作台（未经过登录页）')
  const dash = await evaluate('document.body.innerText')
  check(dash.includes('UI 自动校验'), '工作台列出本项目')
  check(dash.includes('待律师复核'), '状态显示待律师复核')
  const flowSteps = await evaluate(`document.querySelectorAll('.flow-step').length`)
  check(flowSteps === 5, `工作流预览 ${flowSteps} 步`)
  const hasComposer = await evaluate(`!!document.querySelector('.composer textarea') && !!document.querySelector('.composer .send')`)
  check(hasComposer, '工作台对话输入框与发送按钮存在')
  await shot('02-dashboard.png')

  // 2.1 在对话框里发起核查
  const uploadSamples = fs.readdirSync(SAMPLES).filter((f) => f.endsWith('.docx')).slice(0, 2)
  const chooseFiles = async (selector, names) => {
    const r = await send('Runtime.evaluate', { expression: `document.querySelector(${JSON.stringify(selector)})` })
    const result = await send('DOM.setFileInputFiles', {
      objectId: r.result.result.objectId, files: names.map((name) => path.join(SAMPLES, name)),
    })
    if (result.error) throw new Error(JSON.stringify(result.error))
  }
  await chooseFiles('.composer input[type=file]', uploadSamples)
  await waitFor(async () => (await evaluate('document.body.innerText')).includes(uploadSamples[1]))
  check(await evaluate(`document.querySelectorAll('.attachment-list li').length === 2`), '选择附件后立即显示两个文件名')
  check((await evaluate('document.body.innerText')).includes('待上传'), '选择附件明确标注待上传')
  await evaluate(`document.querySelector('.attachment-list button').click()`)
  check(await evaluate(`document.querySelectorAll('.attachment-list li').length === 1`), '提交前可移除附件')
  await chooseFiles('.composer input[type=file]', [uploadSamples[0]])
  await shot('08-attachments-selected.png')
  await send('Network.emulateNetworkConditions', { offline: false, latency: 100, downloadThroughput: -1, uploadThroughput: 16384 })
  await evaluate(`(() => {
    const ta = document.querySelector('.composer textarea')
    const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set
    set.call(ta, '核查核心资产的权属与抵押情况')
    ta.dispatchEvent(new Event('input', { bubbles: true }))
    return true
  })()`)
  await evaluate(`document.querySelector('.composer .send').click()`)
  await waitFor(async () => await evaluate(`(() => { const p = document.querySelector('progress[aria-label="附件总上传进度"]'); return p && p.value > 0 && p.value < 100 })()`), 15000, 100)
  check(true, '真实限速上传显示 0% 与 100% 之间的传输进度')
  check(await evaluate(`[...document.querySelectorAll('.attachment-list button')].every(b => b.disabled)`), '上传过程中禁止移除附件')
  await shot('09-attachments-uploading.png')
  await waitFor(async () => (await evaluate('location.hash'))?.startsWith('#/app/p/'), 15000)
  await send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 })
  await waitFor(async () => (await evaluate('document.body.innerText')).includes(uploadSamples[0]))
  check(await evaluate(`document.querySelectorAll('.filelist li').length === 2`), '上传后项目材料列表保留两个文件名')
  check(true, '在对话框发起核查 → 直接进入项目页')
  await shot('07-new-from-composer.png')

  // 项目页追加上传：断网反馈、保留文件名、恢复上传、刷新版本列表。
  await send('Network.emulateNetworkConditions', { offline: true, latency: 0, downloadThroughput: -1, uploadThroughput: -1 })
  await chooseFiles('input[type=file]', [uploadSamples[0]])
  await waitFor(async () => (await evaluate('document.body.innerText')).includes('上传未完成'))
  check((await evaluate(`document.querySelector('.attachment-list').innerText`)).includes(uploadSamples[0]), '上传失败后保留文件名并显示失败状态')
  await shot('10-attachments-error.png')
  await send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 })
  await chooseFiles('input[type=file]', [uploadSamples[0]])
  await waitFor(async () => (await evaluate('document.body.innerText')).includes('上传完成'))
  await waitFor(async () => await evaluate(`document.querySelectorAll('.vg-row').length === 3 && document.querySelectorAll('.filelist li').length === 3 && !document.querySelector('.page-head .actions button').disabled`))
  check(true, '恢复网络后可重传同名附件，材料与版本列表立即刷新')
  await shot('11-attachments-complete.png')

  await goto(BASE, '进入工作台')
  const loggedIn = await evaluate('document.body.innerText')
  check(loggedIn.includes('退出登录') && loggedIn.includes('进入工作台'), '已登录时首页显示入口与退出登录')

  await goto(`${BASE}/#/app/p/${projectId}`, '风险清单')
  const detail = await evaluate('document.body.innerText')
  check(detail.includes('核心资产权利人非拟上市主体'), '详情页显示风险结论')
  check(detail.includes('质检'), '详情页显示质检结论')
  const cites = await evaluate(`document.querySelectorAll('.evidence blockquote').length`)
  check(cites >= 5, `证据引用渲染 ${cites} 条`)
  const fileInputHidden = await evaluate(`getComputedStyle(document.querySelector('input[type=file]')).display === 'none'`)
  check(fileInputHidden, '文件上传控件已隐藏（不露出裸控件）')
  const reviewItems = await evaluate(`document.querySelectorAll('.review-item').length`)
  check(reviewItems >= 3, `律师复核单列出 ${reviewItems} 项触发条件`)
  check(detail.includes('律师复核'), '详情页显示复核区块')
  const extButton = await evaluate(`[...document.querySelectorAll('.actions button')].some(b => b.textContent.includes('联网核查'))`)
  check(extButton, '项目页有联网核查入口')
  const scoreRows = await evaluate(`document.querySelectorAll('.score-row').length`)
  check(scoreRows >= 4, `评分面板 ${scoreRows} 个维度`)
  const vgRows = await evaluate(`document.querySelectorAll('.vg-row').length`)
  check(vgRows === 7, `材料与版本面板 ${vgRows} 组`)
  const currentChip = await evaluate(`[...document.querySelectorAll('.chip.on')].some(c => c.textContent.includes('当前'))`)
  check(currentChip, '当前版本有明确标记')
  const versionBtn = await evaluate(`[...document.querySelectorAll('.vg-actions button')].some(b => b.textContent.includes('上传新版本'))`)
  check(versionBtn, '可上传新版本')
  await shot('03-project.png')

  // 3) 设置页：配色 / 改密 / API
  await goto(`${BASE}/#/app/settings`, '配色')
  const swatches = await evaluate(`document.querySelectorAll('.theme-swatch').length`)
  check(swatches === 3, `配色可选 ${swatches} 套`)
  const pwdInputs = await evaluate(`document.querySelectorAll('.settings-form input[type=password]').length`)
  check(pwdInputs >= 2, `修改密码表单（${pwdInputs} 个密码框）`)
  const apiFields = await evaluate(`[...document.querySelectorAll('.settings-form input')].length`)
  check(apiFields >= 4, `模型接入表单字段 ${apiFields} 个`)
  await evaluate(`[...document.querySelectorAll('.theme-swatch')].find(b => b.textContent.includes('墨')).click()`)
  await sleep(400)
  const themeNow = await evaluate(`document.documentElement.dataset.theme`)
  check(themeNow === 'ink', `切换配色生效（${themeNow}）`)
  const extFields = await evaluate(`[...document.querySelectorAll('.settings-form label')].some(l => l.textContent.includes('企查查'))`)
  check(extFields, '设置页有企查查/搜索配置项')
  await shot('06-settings.png')

  // 3.1 主体总表
  await goto(`${BASE}/#/app/subjects`, '主体总表')
  const subjectItems = await evaluate(`document.querySelectorAll('.subject-item').length`)
  check(subjectItems >= 1, `主体总表列出 ${subjectItems} 个主体`)
  const subjectDims = await evaluate(`document.querySelectorAll('.score-row').length`)
  check(subjectDims === 5, `主体评分 ${subjectDims} 个维度`)
  await shot('09-subjects.png')

  // 4) 新建核查：三个板块都能选
  await goto(`${BASE}/#/app/new`, '业务板块')
  const boardOptions = await evaluate(`[...document.querySelectorAll('select option')].map(o => o.textContent)`)
  check(boardOptions.length === 3, `三个板块可选：${boardOptions.join('/')}`)

  // 5) 管理员
  await evaluate(`fetch('/api/auth/login',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'admin',password:'123456'})}).then(r=>r.status)`)
  await goto(`${BASE}/#/admin`, '用户与积分')
  const tabs = await evaluate(`[...document.querySelectorAll('.tab')].map(t=>t.textContent).join('|')`)
  check(tabs === '概览|用户与积分|核查要点库|审计日志', `后台标签：${tabs}`)
  await shot('04-admin.png')

  // 4) 要点库页
  await evaluate(`[...document.querySelectorAll('.tab')].find(t=>t.textContent.includes('核查要点库')).click()`)
  await sleep(800)
  const rulesText = await evaluate('document.body.innerText')
  check(rulesText.includes('AST-01') && rulesText.includes('待补'), '要点库显示编号与"待补"状态')
  await shot('05-rules.png')

  ws.close()
}

try {
  const seeded = await seed()
  console.log(`  造数据：项目 #${seeded.projectId}，状态 ${seeded.status}，风险 ${seeded.findings} 条`)
  check(['done', 'pending_review'].includes(seeded.status), `API 侧流水线跑通（${seeded.status}）`)
  check(seeded.findings >= 5, `识别风险 ${seeded.findings} 条`)
  await ui(seeded)
} catch (err) {
  console.error('UI CHECK ERROR:', err.message)
  fails.push(err.message)
} finally {
  try { spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' }) } catch { /* ignore */ }
}

console.log(fails.length ? `\n共 ${total} 项检查，${fails.length} 项失败` : `\n共 ${total} 项检查，全部通过`)
process.exit(fails.length ? 1 : 0)
