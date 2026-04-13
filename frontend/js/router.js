import * as auth from './auth.js'
import { icon } from './icons.js'

const routes = {
  '/login':          () => import('./pages/login.js'),
  '/':               () => import('./pages/products.js'),
  '/products':       () => import('./pages/products.js'),
  '/products/:sku':  () => import('./pages/product-detail.js'),
  '/analytics':      () => import('./pages/analytics.js'),
  '/prompt-library': () => import('./pages/prompt-library.js'),
  '/admin':          () => import('./pages/admin.js'),
  '/manual-generate': () => import('./pages/manual-generate.js'),
  '/activity-log':    () => import('./pages/activity-log.js'),
}

let currentCleanup = null
let sidebarOpen = true

// ── Theme ──────────────────────────────────────────────────────────────────
function getTheme() {
  return localStorage.getItem('theme') || 'light'
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme)
  localStorage.setItem('theme', theme)
}

function toggleTheme() {
  const next = getTheme() === 'dark' ? 'light' : 'dark'
  applyTheme(next)
  render()
}

// Apply saved theme immediately on load
applyTheme(getTheme())

function parseHash() {
  const hash = window.location.hash.replace(/^#/, '') || '/'
  // match /products/:sku
  const detailM = hash.match(/^\/products\/(.+)$/)
  if (detailM) return { route: '/products/:sku', params: { sku: decodeURIComponent(detailM[1]) } }
  return { route: hash.split('?')[0] || '/', params: {} }
}

export function navigate(path) {
  window.location.hash = '#' + path
}

function renderSidebar(user) {
  const nav = [
    { path: '/', label: 'Products',       ico: icon.grid(16) },
    { path: '/prompt-library', label: 'Prompt Library', ico: icon.book(16) },
    { path: '/analytics', label: 'Analytics', ico: icon.chart(16) },
    { path: '/manual-generate', label: 'AI Photoshoot', ico: icon.wand(16) },
    { path: '/activity-log',   label: 'Activity Log',  ico: icon.history(16) },
    ...(user?.role === 'ADMIN' ? [{ path: '/admin', label: 'Admin', ico: icon.settings(16) }] : []),
  ]

  const { route } = parseHash()
  const activePath = route === '/products/:sku' ? '/' : route
  const isDark = getTheme() === 'dark'

  return `
    <aside id="sidebar" class="${sidebarOpen ? 'sidebar open' : 'sidebar'}">
      <div class="sidebar-logo">
        <div class="logo-icon">${icon.sparkles(14)}</div>
        ${sidebarOpen ? `<div><div class="logo-title">ImageGen</div><div class="logo-sub">Local</div></div>` : ''}
      </div>

      <nav class="sidebar-nav">
        ${nav.map(n => `
          <a href="#${n.path}" class="nav-link ${activePath === n.path ? 'active' : ''}">
            <span class="nav-icon">${n.ico}</span>
            ${sidebarOpen ? `<span class="nav-label">${n.label}</span>` : ''}
          </a>
        `).join('')}
      </nav>

      <div class="sidebar-footer">
        ${sidebarOpen && user ? `
          <div class="sidebar-user">
            <div class="user-avatar">${icon.user(13)}</div>
            <div class="user-info">
              <div class="user-name">${user.full_name || ''}</div>
              <div class="user-role">${user.role || ''}</div>
            </div>
          </div>
        ` : ''}
        <button id="btn-theme-toggle" class="nav-link" title="${isDark ? 'Switch to light mode' : 'Switch to dark mode'}">
          <span class="nav-icon">${isDark ? icon.sun(14) : icon.moon(14)}</span>
          ${sidebarOpen ? `<span class="nav-label">${isDark ? 'Light Mode' : 'Dark Mode'}</span>` : ''}
        </button>
        <button id="btn-logout" class="nav-link logout-btn">
          <span class="nav-icon">${icon.logout(14)}</span>
          ${sidebarOpen ? '<span class="nav-label">Sign out</span>' : ''}
        </button>
        <button id="btn-toggle-sidebar" class="sidebar-toggle">
          ${sidebarOpen ? icon.chevLeft(14) : icon.chevRight(14)}
        </button>
      </div>
    </aside>
  `
}

async function render() {
  if (currentCleanup) { currentCleanup(); currentCleanup = null }

  const { route, params } = parseHash()
  const app = document.getElementById('app')
  const user = auth.getUser()

  // Login page — no sidebar
  if (route === '/login') {
    if (!app) return
    app.innerHTML = '<div id="page"></div>'
    const mod = await import('./pages/login.js')
    currentCleanup = await mod.render(document.getElementById('page'), params) || null
    return
  }

  // Auth guard
  if (!auth.isAuthenticated()) {
    navigate('/login')
    return
  }

  // Admin guard
  if (route === '/admin' && user?.role !== 'ADMIN') {
    navigate('/')
    return
  }

  // App shell with sidebar
  app.innerHTML = `
    <div class="app-shell">
      ${renderSidebar(user)}
      <main id="main-content" class="main-content"></main>
    </div>
  `

  // Sidebar interactions
  document.getElementById('btn-theme-toggle')?.addEventListener('click', toggleTheme)
  document.getElementById('btn-logout')?.addEventListener('click', () => auth.logout())
  document.getElementById('btn-toggle-sidebar')?.addEventListener('click', () => {
    sidebarOpen = !sidebarOpen
    render()
  })

  // Highlight active link on nav click
  document.querySelectorAll('.nav-link').forEach(a => {
    a.addEventListener('click', () => setTimeout(render, 0))
  })

  const main = document.getElementById('main-content')
  const loader = routes[route]
  if (!loader) { main.innerHTML = '<div class="p-8 text-dim">Page not found</div>'; return }

  const mod = await loader()
  currentCleanup = await mod.render(main, params) || null
}

window.addEventListener('hashchange', render)
window.addEventListener('DOMContentLoaded', render)
