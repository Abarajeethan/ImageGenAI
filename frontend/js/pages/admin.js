import { adminApi } from '../api.js'
import { toast } from '../toast.js'
import { icon } from '../icons.js'

export async function render(container) {
  let tab = 'users'
  let users = [], brands = [], audit = []

  async function loadAll() {
    try {
      [users, brands, audit] = await Promise.all([
        adminApi.users(), adminApi.brands(), adminApi.auditTrail()
      ])
    } catch { toast.error('Failed to load admin data') }
    renderPage()
  }

  function renderPage() {
    container.innerHTML = `
      <div class="page-content">
        <div class="page-header">
          <h1 class="page-title">Admin</h1>
        </div>
        <div class="tabs">
          ${['users','brands','audit','dev'].map(t => `
            <button class="tab-btn ${tab === t ? 'active' : ''}" data-tab="${t}">
              ${t === 'dev' ? '🛠 Dev Tools' : t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          `).join('')}
        </div>
        <div id="tab-content" style="margin-top:16px;">${renderTab()}</div>
      </div>
    `

    container.querySelectorAll('.tab-btn').forEach(b => b.addEventListener('click', () => {
      tab = b.dataset.tab; renderPage()
    }))

    attachTabEvents()
  }

  function renderTab() {
    if (tab === 'users')  return renderUsers()
    if (tab === 'brands') return renderBrands()
    if (tab === 'audit')  return renderAudit()
    if (tab === 'dev')    return renderDevTools()
    return ''
  }

  function renderUsers() {
    return `
      <div class="card" style="overflow:auto;">
        <table class="data-table">
          <thead><tr>
            <th>Name</th><th>Email</th><th>Role</th><th>Last Login</th><th>Active</th>
          </tr></thead>
          <tbody>
            ${users.map(u => `
              <tr>
                <td style="padding:10px 12px;">${u.full_name}</td>
                <td style="padding:10px 12px;" class="mono text-dim">${u.email}</td>
                <td style="padding:10px 12px;">
                  <select class="input" style="width:120px;" data-user-id="${u.id}" data-field="role">
                    ${['VIEWER','EDITOR','ADMIN'].map(r => `<option ${u.role === r ? 'selected' : ''}>${r}</option>`).join('')}
                  </select>
                </td>
                <td style="padding:10px 12px;" class="text-dim">${u.last_login_at ? new Date(u.last_login_at).toLocaleDateString() : '—'}</td>
                <td style="padding:10px 12px;">
                  <label class="toggle-label">
                    <input type="checkbox" class="toggle-check" data-user-id="${u.id}" data-field="is_active" ${u.is_active ? 'checked' : ''}>
                    <span class="toggle-slider"></span>
                  </label>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `
  }

  function renderBrands() {
    return `
      <div class="card" style="overflow:auto;">
        <table class="data-table">
          <thead><tr>
            <th>Brand Name</th><th>AI Forbidden</th>
          </tr></thead>
          <tbody>
            ${brands.map(b => `
              <tr>
                <td style="padding:10px 12px;">${b.brand_name}</td>
                <td style="padding:10px 12px;">
                  <label class="toggle-label">
                    <input type="checkbox" class="toggle-check" data-brand-id="${b.id}" data-field="ai_forbidden" ${b.ai_forbidden ? 'checked' : ''}>
                    <span class="toggle-slider"></span>
                  </label>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `
  }

  function renderAudit() {
    return `
      <div class="card" style="overflow:auto;">
        <table class="data-table">
          <thead><tr>
            <th>Time</th><th>User</th><th>Action</th><th>SKU</th>
          </tr></thead>
          <tbody>
            ${audit.map(a => `
              <tr>
                <td style="padding:10px 12px;" class="text-dim mono">${new Date(a.occurred_at).toLocaleString()}</td>
                <td style="padding:10px 12px;">${a.user?.full_name || '—'}</td>
                <td style="padding:10px 12px;"><span class="tag tag-blue">${a.action.replace(/_/g, ' ')}</span></td>
                <td style="padding:10px 12px;" class="mono text-dim">${a.sku_id || '—'}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `
  }

  function renderDevTools() {
    return `
      <div class="card" style="padding:24px;max-width:600px;">
        <div class="section-title" style="margin-bottom:16px;">Developer Tools</div>

        <div style="display:flex;flex-direction:column;gap:12px;">
          <div class="card" style="padding:16px;background:rgba(99,102,241,0.05);border-color:rgba(99,102,241,0.2);">
            <div style="font-weight:600;margin-bottom:4px;">Step 1 — Import Product Data</div>
            <div class="text-dim" style="font-size:12px;margin-bottom:12px;">
              Place your Excel file at <code class="mono" style="background:rgba(255,255,255,0.06);padding:1px 5px;border-radius:4px;">backend/data/products.xlsx</code>
              then click Import. Idempotent — safe to run multiple times.
            </div>
            <button id="btn-import-excel" class="btn btn-primary">📥 Import Excel Data</button>
          </div>

          <div class="card" style="padding:16px;background:rgba(34,197,94,0.05);border-color:rgba(34,197,94,0.2);">
            <div style="font-weight:600;margin-bottom:4px;">Step 2 — Generate AI Images</div>
            <div class="text-dim" style="font-size:12px;margin-bottom:12px;">
              Kicks off AI generation for all PENDING_AI products.
              Go to Products to watch them update in real time.
            </div>
            <button id="btn-gen-all" class="btn" style="background:linear-gradient(135deg,#059669,#10b981);color:#fff;">${icon.sparkles(14)} Generate All Pending</button>
          </div>
        </div>
      </div>
    `
  }

  function attachTabEvents() {
    container.querySelectorAll('select[data-user-id]').forEach(sel => {
      sel.addEventListener('change', async () => {
        try {
          await adminApi.updateUser(sel.dataset.userId, { [sel.dataset.field]: sel.value })
          toast.success('Updated')
        } catch (err) { toast.error(err.message || 'Failed') }
      })
    })
    container.querySelectorAll('.toggle-check[data-user-id]').forEach(cb => {
      cb.addEventListener('change', async () => {
        try {
          await adminApi.updateUser(cb.dataset.userId, { [cb.dataset.field]: cb.checked })
          toast.success('Updated')
        } catch (err) { toast.error(err.message || 'Failed') }
      })
    })
    container.querySelectorAll('.toggle-check[data-brand-id]').forEach(cb => {
      cb.addEventListener('change', async () => {
        try {
          await adminApi.updateBrand(cb.dataset.brandId, { [cb.dataset.field]: cb.checked })
          toast.success('Updated')
        } catch (err) { toast.error(err.message || 'Failed') }
      })
    })

    container.querySelector('#btn-import-excel')?.addEventListener('click', async () => {
      const btn = container.querySelector('#btn-import-excel')
      btn.disabled = true; btn.textContent = 'Importing…'
      try {
        const res = await adminApi.importExcel()
        const c = res.created
        toast.success(`Import complete — ${c.products} product(s), ${c.brands} brand(s) created`)
        import('../router.js').then(m => m.navigate('/'))
      } catch (err) { toast.error(err.message || 'Import failed') }
      finally { btn.disabled = false; btn.textContent = '📥 Import Excel Data' }
    })

    container.querySelector('#btn-gen-all')?.addEventListener('click', async () => {
      const btn = container.querySelector('#btn-gen-all')
      btn.disabled = true; btn.textContent = 'Starting…'
      try {
        const res = await adminApi.generateAllPending()
        toast.success(res.message || `Generation started for ${res.queued} products`)
        import('../router.js').then(m => m.navigate('/'))
      } catch (err) { toast.error(err.message || 'Failed') }
      finally { btn.disabled = false; btn.innerHTML = `${icon.sparkles(14)} Generate All Pending` }
    })
  }

  container.innerHTML = `<div class="loading">${icon.loader(24)}<span>Loading admin data...</span></div>`
  await loadAll()
}
