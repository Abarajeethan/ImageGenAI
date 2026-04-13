const KEY = 'imagegen-auth'

function load() {
  try { return JSON.parse(localStorage.getItem(KEY) || 'null') || {} }
  catch { return {} }
}

function save(data) {
  localStorage.setItem(KEY, JSON.stringify(data))
}

export function getToken()         { return load().accessToken || null }
export function getRefreshToken()  { return load().refreshToken || null }
export function getUser()          { return load().user || null }
export function isAuthenticated()  { return !!load().accessToken }

export function setAuth(accessToken, refreshToken, user) {
  save({ accessToken, refreshToken, user })
}

export function setTokens(accessToken, refreshToken) {
  const d = load()
  save({ ...d, accessToken, refreshToken })
}

export function logout() {
  localStorage.removeItem(KEY)
  window.location.hash = '#/login'
}
