const BASE = ''

// Upload events report transferred bytes; only a successful response means processing is complete.
function uploadForm(path, body, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', BASE + path)
    xhr.withCredentials = true
    xhr.upload.onprogress = (event) => {
      onProgress?.({ phase: 'uploading', percent: event.lengthComputable
        ? Math.min(100, Math.floor(event.loaded / event.total * 100)) : null })
    }
    xhr.upload.onload = () => onProgress?.({ phase: 'processing', percent: 100 })
    const fail = (message) => {
      onProgress?.({ phase: 'error' })
      reject(new Error(message))
    }
    xhr.onerror = () => fail('网络连接失败，请检查连接后重试')
    xhr.onabort = () => fail('上传已取消')
    xhr.onload = () => {
      let payload
      try { payload = JSON.parse(xhr.responseText) } catch { /* handled below */ }
      if (xhr.status < 200 || xhr.status >= 300) {
        const message = payload?.detail || payload?.message || `上传失败（HTTP ${xhr.status}）`
        fail(typeof message === 'string' ? message : JSON.stringify(message))
      } else if (!payload) {
        fail('上传响应异常，请查看项目材料确认上传结果')
      } else {
        onProgress?.({ phase: 'done', percent: 100 })
        resolve(payload)
      }
    }
    onProgress?.({ phase: 'uploading', percent: 0 })
    xhr.send(body)
  })
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) }
  if (!(options.body instanceof FormData)) headers['Content-Type'] = 'application/json'
  const res = await fetch(BASE + path, { credentials: 'include', ...options, headers })
  const isJson = (res.headers.get('content-type') || '').includes('application/json')
  const payload = isJson ? await res.json() : null
  if (!res.ok) {
    const msg = (payload && (payload.detail || payload.message)) || `请求失败（HTTP ${res.status}）`
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return payload
}

export const api = {
  me: () => request('/api/auth/me'),
  login: (email, password) =>
    request('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  register: (email, password) =>
    request('/api/auth/register', { method: 'POST', body: JSON.stringify({ email, password }) }),
  logout: () => request('/api/auth/logout', { method: 'POST' }),
  changePassword: (oldPassword, newPassword) =>
    request('/api/auth/password', {
      method: 'POST',
      body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
    }),
  credits: (limit = 20) => request(`/api/credits?limit=${limit}`),
  llmPing: (cfg) => request('/api/llm/ping', { method: 'POST', body: JSON.stringify(cfg) }),
  reviewDecision: (id, decision, comment = '') =>
    request(`/api/reviews/${id}/decision`, { method: 'POST', body: JSON.stringify({ decision, comment }) }),
  externalCheck: (id, headers = {}) =>
    request(`/api/projects/${id}/external-check`, { method: 'POST', headers }),
  subjects: () => request('/api/subjects'),
  subjectScore: (name) => request(`/api/subjects/score?name=${encodeURIComponent(name)}`),
  projects: () => request('/api/projects'),
  createProject: (data) => request('/api/projects', { method: 'POST', body: JSON.stringify(data) }),
  project: (id) => request(`/api/projects/${id}`),
  deleteProject: (id) => request(`/api/projects/${id}`, { method: 'DELETE' }),
  score: (id) => request(`/api/projects/${id}/score`),
  upload: (id, files, onProgress) => {
    const fd = new FormData()
    for (const f of files) fd.append('files', f)
    return uploadForm(`/api/projects/${id}/documents`, fd, onProgress)
  },
  run: (id, headers = {}) => request(`/api/projects/${id}/run`, { method: 'POST', headers }),
  progress: (id) => request(`/api/projects/${id}/progress`),
  reset: (id) => request(`/api/projects/${id}/reset`, { method: 'POST' }),
  revise: (fid, status) =>
    request(`/api/findings/${fid}`, { method: 'PATCH', body: JSON.stringify({ status }) }),
  overview: () => request('/api/admin/overview'),
  users: () => request('/api/admin/users'),
  addCredits: (id, delta) =>
    request(`/api/admin/users/${id}/credits`, { method: 'POST', body: JSON.stringify({ delta, reason: '管理员调整' }) }),
  rules: () => request('/api/admin/rules'),
  audit: () => request('/api/admin/audit'),
  adminProjects: () => request('/api/admin/projects'),
  versions: (id) => request(`/api/projects/${id}/versions`),
  uploadVersion: (id, groupId, file, onProgress) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('group_id', String(groupId))
    return uploadForm(`/api/projects/${id}/versions`, fd, onProgress)
  },
  versionDiff: (a, b) => request(`/api/versions/${a}/diff/${b}`),
  reportUrl: (id) => `/api/projects/${id}/report`,
}
