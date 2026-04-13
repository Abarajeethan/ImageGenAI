let container = null

function getContainer() {
  if (!container) {
    container = document.createElement('div')
    container.id = 'toasts'
    container.style.cssText = `
      position:fixed; top:16px; right:16px; z-index:9999;
      display:flex; flex-direction:column; gap:8px; pointer-events:none;
    `
    document.body.appendChild(container)
  }
  return container
}

function show(message, type = 'info') {
  const el = document.createElement('div')
  const colors = {
    success: 'rgba(34,197,94,0.15)',
    error:   'rgba(239,68,68,0.15)',
    info:    'rgba(99,102,241,0.15)',
  }
  const borders = {
    success: 'rgba(34,197,94,0.3)',
    error:   'rgba(239,68,68,0.3)',
    info:    'rgba(99,102,241,0.3)',
  }
  el.style.cssText = `
    padding:10px 14px; border-radius:8px; font-size:13px; font-weight:500;
    color:#fafafa; pointer-events:auto; max-width:320px;
    background:${colors[type]}; border:1px solid ${borders[type]};
    backdrop-filter:blur(12px);
    animation:toastIn 0.2s ease; white-space:pre-wrap; word-break:break-word;
  `
  el.textContent = message
  getContainer().appendChild(el)
  setTimeout(() => {
    el.style.animation = 'toastOut 0.2s ease forwards'
    setTimeout(() => el.remove(), 200)
  }, 3000)
}

export const toast = {
  success: (msg) => show(msg, 'success'),
  error:   (msg) => show(msg, 'error'),
  info:    (msg) => show(msg, 'info'),
}
