// 主题、模型与外部数据源配置（只存浏览器，不上送服务器持久化）
export const THEMES = [
  { id: 'navy', name: '藏青', desc: '默认' },
  { id: 'ink', name: '墨', desc: '近黑' },
  { id: 'moss', name: '苔', desc: '深绿' },
]

const THEME_KEY = 'lawlens.theme'
const API_KEY = 'lawlens.api'
const EXT_KEY = 'lawlens.external'

export function getTheme() {
  try {
    return localStorage.getItem(THEME_KEY) || 'navy'
  } catch {
    return 'navy'
  }
}

export function applyTheme(id) {
  document.documentElement.dataset.theme = id
  try { localStorage.setItem(THEME_KEY, id) } catch { /* 隐私模式忽略 */ }
}

export function loadApi() {
  try {
    return JSON.parse(localStorage.getItem(API_KEY) || '{}')
  } catch {
    return {}
  }
}

export function saveApi(cfg) {
  try { localStorage.setItem(API_KEY, JSON.stringify(cfg)) } catch { /* ignore */ }
}

export function llmHeaders() {
  const { key, model, base } = loadApi()
  const headers = {}
  if (key) headers['X-LLM-Key'] = key
  if (model) headers['X-LLM-Model'] = model
  if (base) headers['X-LLM-Base'] = base
  return headers
}

export function loadExternal() {
  try {
    return JSON.parse(localStorage.getItem(EXT_KEY) || '{}')
  } catch {
    return {}
  }
}

export function saveExternal(cfg) {
  try { localStorage.setItem(EXT_KEY, JSON.stringify(cfg)) } catch { /* ignore */ }
}

export function externalHeaders() {
  const { qccKey, qccSecret, provider, searchKey } = loadExternal()
  const headers = {}
  if (qccKey) headers['X-QCC-Key'] = qccKey
  if (qccSecret) headers['X-QCC-Secret'] = qccSecret
  if (provider) headers['X-Search-Provider'] = provider
  if (searchKey) headers['X-Search-Key'] = searchKey
  return headers
}
