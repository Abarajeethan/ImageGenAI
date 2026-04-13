import { authApi } from '../api.js'
import * as auth from '../auth.js'
import { toast } from '../toast.js'
import { icon } from '../icons.js'
import { navigate } from '../router.js'

export async function render(container) {
  if (auth.isAuthenticated()) { navigate('/'); return }

  container.innerHTML = `
    <div class="login-page">
      <div class="login-box">
        <div class="login-header">
          <div class="login-logo">${icon.sparkles(24)}</div>
          <h1 class="login-title">ImageGen Local</h1>
          <p class="login-sub">AI Image Generation Tool</p>
        </div>

        <form id="login-form" class="card login-form">
          <div class="field">
            <label class="label">Username / Email</label>
            <input id="inp-user" type="text" class="input" placeholder="admin@example.com" autocomplete="username" autofocus>
          </div>
          <div class="field">
            <label class="label">Password</label>
            <div class="pw-wrap">
              <input id="inp-pw" type="password" class="input" placeholder="••••••••" autocomplete="current-password">
              <button type="button" id="btn-show-pw" class="pw-toggle">${icon.eye(14)}</button>
            </div>
          </div>
          <button type="submit" id="btn-login" class="btn btn-primary btn-block">Sign in</button>
        </form>

        <p class="login-hint">Default: admin@example.com / admin123</p>
      </div>
    </div>
  `

  let showPw = false
  container.querySelector('#btn-show-pw').addEventListener('click', () => {
    showPw = !showPw
    const inp = container.querySelector('#inp-pw')
    inp.type = showPw ? 'text' : 'password'
    container.querySelector('#btn-show-pw').innerHTML = showPw ? icon.eyeOff(14) : icon.eye(14)
  })

  container.querySelector('#login-form').addEventListener('submit', async (e) => {
    e.preventDefault()
    const username = container.querySelector('#inp-user').value.trim()
    const password = container.querySelector('#inp-pw').value
    if (!username || !password) return

    const btn = container.querySelector('#btn-login')
    btn.disabled = true
    btn.innerHTML = `<span class="spin">${icon.loader(15)}</span> Signing in...`

    try {
      const data = await authApi.login(username, password)
      const meRes = await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${data.access_token}` }
      })
      const user = await meRes.json()
      auth.setAuth(data.access_token, data.refresh_token, user)
      navigate('/')
    } catch (err) {
      toast.error(err.message || 'Login failed')
      btn.disabled = false
      btn.innerHTML = 'Sign in'
    }
  })
}
