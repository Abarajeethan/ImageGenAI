import * as auth from './auth.js'

const BASE = '/api'

let refreshing = null

async function request(method, path, { body, params } = {}) {
  let url = BASE + path
  if (params) {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => { if (v != null && v !== '') q.append(k, v) })
    const qs = q.toString()
    if (qs) url += '?' + qs
  }
  const headers = { 'Content-Type': 'application/json' }
  const token = auth.getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(url, {
    method,
    headers,
    body: body != null ? JSON.stringify(body) : undefined,
  })

  if (res.status === 401) {
    if (!refreshing) {
      refreshing = doRefresh()
    }
    const ok = await refreshing
    refreshing = null
    if (ok) return request(method, path, { body, params })
    auth.logout()
    throw new Error('Session expired')
  }

  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail || detail } catch {}
    throw Object.assign(new Error(detail), { status: res.status })
  }

  if (res.status === 204) return null
  return res.json()
}

async function doRefresh() {
  const rt = auth.getRefreshToken()
  if (!rt) return false
  try {
    const data = await fetch(BASE + '/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: rt }),
    }).then(r => r.json())
    auth.setTokens(data.access_token, data.refresh_token)
    return true
  } catch {
    return false
  }
}

const get   = (path, opts) => request('GET',   path, opts)
const post  = (path, body) => request('POST',  path, { body })
const patch = (path, body) => request('PATCH', path, { body })

async function postForm(path, formData) {
  const headers = {}
  const token = auth.getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(BASE + path, { method: 'POST', headers, body: formData })
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail || detail } catch {}
    throw Object.assign(new Error(detail), { status: res.status })
  }
  return res.json()
}

export const authApi = {
  login: (username, password) => post('/auth/login', { username, password }),
  me:    ()                   => get('/auth/me'),
}

export const productsApi = {
  list:        (params) => get('/products', { params }),
  get:         (sku)    => get(`/products/${sku}`),
  select:      (sku, selected) => patch(`/products/${sku}/select`, { selected }),
  seasons:     ()       => get('/products/seasons'),
  colours:     ()       => get('/products/colours'),
  campaigns:   ()       => get('/products/campaigns'),
  departments: ()       => get('/products/departments'),
}

export const promptsApi = {
  get:            (sku)       => get(`/products/${sku}/prompt`),
  update:         (sku, text) => patch(`/products/${sku}/prompt`, { prompt_text: text }),
  history:        (sku)       => get(`/products/${sku}/prompt/history`),
  regenerate:     (sku)       => post(`/products/${sku}/regenerate`),
  generateAI:     (sku)       => post(`/products/${sku}/generate-prompt`),
  listLibrary:    ()          => get('/prompt-library'),
  getSystemPrompt:()          => get('/prompt-library/system-prompt'),
  createLibrary:  (data)      => post('/prompt-library', data),
  updateLibrary:  (id, data)  => patch(`/prompt-library/${id}`, data),
  manualGenerate: (sku, fd)   => postForm(`/products/${sku}/manual-generate`, fd),
  standaloneGenerate: (fd)    => postForm('/generate/manual', fd),
}

export const approvalsApi = {
  approve: (sku, keys)        => post(`/products/${sku}/approve`, { keys }),
  recall:  (sku, key, reason) => post(`/products/${sku}/recall`, { key, reason }),
  reject:  (sku, key)         => post(`/products/${sku}/reject-ai-image`, { key }),
  reorder: (sku, aiKeys)      => patch(`/products/${sku}/image-order`, { ai_keys: aiKeys }),
}

export const analyticsApi = {
  summary: (days = 30) => get('/analytics/summary', { params: { days } }),
}

export const adminApi = {
  users:              ()          => get('/admin/users'),
  updateUser:         (id, data)  => patch(`/admin/users/${id}`, data),
  brands:             ()          => get('/admin/brands'),
  updateBrand:        (id, data)  => patch(`/admin/brands/${id}`, data),
  auditTrail:         (params)    => get('/admin/audit-trail', { params }),
  generateAllPending: ()          => post('/admin/generate-all-pending'),
  importExcel:        ()          => post('/admin/import-excel'),
}
