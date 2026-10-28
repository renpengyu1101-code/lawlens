/** 界面自检：真实浏览器、两个视口；输出检查表 + 截图。用法：node scripts/ui_audit.mjs <baseUrl> <outDir> */
import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'

const BASE = process.argv[2] || 'http://127.0.0.1:8010'
const OUT = process.argv[3] || 'shots-audit'
fs.mkdirSync(OUT, { recursive: true })

const VIEWPORTS = [
  { name: '1440x900', w: 1440, h: 900 },
  { name: '1120x780', w: 1120, h: 780 },
]

const CHECK_JS = `(() => {
  const checks = [];
  const add = (name, ok, detail) => checks.push({ name, ok: !!ok, detail: String(detail) });
  const vis = (el) => !!el && el.offsetWidth > 0 && el.offsetHeight > 0;
  const rect = (el) => { const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height, r: r.right, b: r.bottom }; };
  const overlap = (a, b) => {
    const x = Math.max(0, Math.min(a.r, b.r) - Math.max(a.x, b.x));
    const y = Math.max(0, Math.min(a.b, b.b) - Math.max(a.y, b.y));
    return Math.round(x * y);
  };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const parse = (s) => (s.match(/[\\d.]+/g) || []).map(Number);
  const contrast = (fg, bg) => { const a = lum(fg), b = lum(bg); return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05); };
  const solidBg = (el) => {
    let node = el, best = [241, 239, 234];
    while (node && node !== document.documentElement) {
      const c = getComputedStyle(node).backgroundColor;
      const p = parse(c);
      if (p.length >= 3 && (p[3] === undefined || p[3] > 0.9)) { best = p.slice(0, 3); break; }
      node = node.parentElement;
    }
    return best;
  };

  // 1 横向溢出
  add('无横向溢出', document.documentElement.scrollWidth - innerWidth <= 1, (document.documentElement.scrollWidth - innerWidth) + 'px');

  // 2 主按钮：尺寸与对比度
  const send = document.querySelector('.composer .send');
  if (vis(send)) {
    add('主按钮高度 >= 44', send.offsetHeight >= 44, send.offsetWidth + '×' + send.offsetHeight);
    const cs = getComputedStyle(send);
    const fg = parse(cs.color).slice(0, 3), bg = parse(cs.backgroundColor).slice(0, 3);
    const ratio = contrast(fg, bg);
    add('主按钮文字对比度 >= 4.5', ratio >= 4.5, ratio.toFixed(2) + ':1');
  } else add('主按钮可见', false, 'not found');

  // 3 次级按钮/链接点击区 >= 32
  const small = [...document.querySelectorAll('.btn, .nav a, .meta-chip')].filter(vis);
  const tiny = small.filter((el) => el.offsetHeight < 32);
  add('点击区 >= 32px', tiny.length === 0, tiny.length ? tiny.length + ' 个偏小' : small.length + ' 个元素');

  // 4 按钮文字裁切
  const clipped = [...document.querySelectorAll('.btn, .badge, .meta-chip, .nav a')].filter((el) => vis(el) && el.scrollWidth > el.clientWidth + 2);
  add('文字未被裁切', clipped.length === 0, clipped.length ? clipped.map((e) => e.textContent.trim().slice(0, 8)).join('/') : 'ok');

  // 5 交互元素互不重叠
  const clickable = [...document.querySelectorAll('.nav a, .composer .btn, .topbar .btn, .meta-chip, .page-head .btn')].filter(vis).map(rect);
  let worst = 0, worstPair = '';
  for (let i = 0; i < clickable.length; i++) for (let j = i + 1; j < clickable.length; j++) {
    const a = overlap(clickable[i], clickable[j]);
    if (a > worst) { worst = a; worstPair = i + '-' + j; }
  }
  add('可点元素互不重叠', worst === 0, worst ? worst + 'px² (' + worstPair + ')' : 'ok');

  // 6 卡片不压住可点区域（透镜是装饰，允许被卡片覆盖；输入框必须干净）
  const composer = document.querySelector('.composer');
  if (vis(composer)) {
    const cards = [...document.querySelectorAll('.side-card')].filter(vis).map(rect);
    const cr = rect(composer);
    const hits = cards.filter((c) => overlap(c, cr) > 0).length;
    add('卡片不遮挡输入区', hits === 0, hits + ' 张');
  }

  // 7 关键文字对比度（正文/说明）
  const bodyText = document.querySelector('.auth-sub, .status-note, .hero-note p, .dash-sub');
  if (vis(bodyText)) {
    const cs = getComputedStyle(bodyText);
    const ratio = contrast(parse(cs.color).slice(0, 3), solidBg(bodyText));
    add('说明文字对比度 >= 4.5', ratio >= 4.5, ratio.toFixed(2) + ':1');
  }

  // 8 同组卡片对齐：宽屏三列要求同列对齐；窄屏两列网格只要求不重叠、同列间距成 4 的倍数
  const leftCards = [...document.querySelectorAll('.hero-col.left .side-card')].filter(vis).map(rect);
  const rightCards = [...document.querySelectorAll('.hero-col.right .side-card')].filter(vis).map(rect);
  const allCards = [...leftCards, ...rightCards];
  const wide = innerWidth > 1280;
  if (wide) {
    if (leftCards.length) add('左栏卡片左缘对齐', new Set(leftCards.map((c) => Math.round(c.x))).size === 1, [...new Set(leftCards.map((c) => Math.round(c.x)))].join(','));
    if (rightCards.length) add('右栏卡片右缘对齐', new Set(rightCards.map((c) => Math.round(c.r))).size === 1, [...new Set(rightCards.map((c) => Math.round(c.r)))].join(','));
    if (leftCards.length > 1) {
      const gaps = leftCards.slice(1).map((c, i) => Math.round(c.y) - Math.round(leftCards[i].b));
      // 栏内用 space-between 撑满高度：要求各段间距一致（±1px），节奏稳定即可
      add('左栏间距一致', Math.max(...gaps) - Math.min(...gaps) <= 1, gaps.join(','));
    }
  } else {
    let worstCard = 0;
    for (let i = 0; i < allCards.length; i++) for (let j = i + 1; j < allCards.length; j++) worstCard = Math.max(worstCard, overlap(allCards[i], allCards[j]));
    add('窄屏卡片互不重叠', worstCard === 0, worstCard + 'px²');
    // 逐栏、逐列比较间距（跨栏不做比较），允许 1px 的亚像素误差
    const badGaps = [];
    for (const rail of [leftCards, rightCards]) {
      const columns = {};
      for (const c of rail) (columns[Math.round(c.x)] = columns[Math.round(c.x)] || []).push(c);
      for (const col of Object.values(columns)) {
        for (let i = 1; i < col.length; i++) {
          const g = Math.round(col[i].y) - Math.round(col[i - 1].b);
          if (Math.abs(g - Math.round(g / 4) * 4) > 1) badGaps.push(g);
        }
      }
    }
    add('窄屏同列间距为 4 的倍数', badGaps.length === 0, badGaps.join(',') || 'ok');
  }

  // 10 内容不被顶栏遮住
  const topbar = document.querySelector('.topbar');
  const h1 = document.querySelector('.dash h1, .page h1');
  if (vis(topbar) && vis(h1)) add('标题未被顶栏遮挡', rect(h1).y >= rect(topbar).b, Math.round(rect(h1).y) + ' / ' + Math.round(rect(topbar).b));

  return { checks };
})()`

const child = spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', [
  '--headless=new', '--remote-debugging-port=9879', `--user-data-dir=${path.join(os.tmpdir(), 'chrome-qa-' + Date.now())}`,
  '--no-first-run', '--disable-gpu', '--hide-scrollbars', '--window-size=1440,900', 'about:blank',
], { stdio: 'ignore' })

const waitFor = async (fn, t = 20000) => { const t0 = Date.now(); while (Date.now() - t0 < t) { try { const v = await fn(); if (v) return v } catch { /* retry */ } await sleep(200) } throw new Error('timeout') }

try {
  await waitFor(async () => (await fetch('http://127.0.0.1:9879/json/version')).ok)
  const target = await (await fetch('http://127.0.0.1:9879/json/new?about:blank', { method: 'PUT' })).json()
  const ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej })
  let seq = 0
  const pending = new Map()
  ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } }
  const send = (method, params = {}) => new Promise((res) => { const id = ++seq; pending.set(id, res); ws.send(JSON.stringify({ id, method, params })) })
  const evaluate = async (e) => { const r = await send('Runtime.evaluate', { expression: e, awaitPromise: true, returnByValue: true }); return r.result?.result?.value }

  await send('Page.enable'); await send('Runtime.enable')
  await send('Page.navigate', { url: `${BASE}/#/` }); await sleep(700)
  await evaluate(`fetch('/api/auth/login',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'demo@lawlens.test',password:'demo123456'})}).then(r=>r.status)`)

  let failed = 0
  for (const vp of VIEWPORTS) {
    await send('Emulation.setDeviceMetricsOverride', { width: vp.w, height: vp.h, deviceScaleFactor: 1, mobile: false })
    await send('Page.navigate', { url: 'about:blank' }); await sleep(200)
    await send('Page.navigate', { url: `${BASE}/#/app` }); await sleep(1800)
    const res = await evaluate(CHECK_JS)
    console.log(`\n### ${vp.name}`)
    for (const c of res.checks) {
      if (!c.ok) failed++
      console.log(`${c.ok ? 'PASS' : 'FAIL'}  ${c.name}  ${c.detail}`)
    }
    const shot = await send('Page.captureScreenshot', { format: 'png', fromSurface: true })
    fs.writeFileSync(path.join(OUT, `qa-${vp.name}.png`), Buffer.from(shot.result.data, 'base64'))
  }
  console.log(`\n${failed === 0 ? 'ALL PASS' : failed + ' FAILED'}`)
  ws.close()
  process.exitCode = failed === 0 ? 0 : 1
} finally {
  try { spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' }) } catch { /* ignore */ }
}
