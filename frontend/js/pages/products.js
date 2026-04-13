import { productsApi, adminApi } from '../api.js'
import { toast } from '../toast.js'
import { icon } from '../icons.js'
import { navigate } from '../router.js'
import { getUser } from '../auth.js'

const STATUSES = [
  { value: '', label: 'All statuses' },
  { value: 'PENDING_AI', label: 'Pending AI' },
  { value: 'AI_GENERATING', label: 'AI Generating' },
  { value: 'AI_READY', label: 'AI Ready' },
  { value: 'AI_FAILED', label: 'AI Failed' },
  { value: 'USER_SELECTED', label: 'User Selected' },
  { value: 'APPROVED', label: 'Approved' },
]

let filters = { search: '', season: '', brand_id: '', status: '', text_approval_date: '', ingestion_date: '', campaign_name: '', department: '', stock_level: '', category_id: '', page: 1, page_size: 30 }
let viewMode = 'grid'
let brands = []
let seasons = []
let campaigns = []
let categories = []
let departments = []
let pollTimer = null

function statusLabel(s) { return s.replace(/_/g, ' ') }

function productCard(p) {
  const isGenerating = p.status === 'AI_GENERATING'
  const urls = p.preview_urls?.length ? p.preview_urls : (p.thumbnail_url ? [p.thumbnail_url] : [])

  let thumbContent
  if (urls.length === 0) {
    thumbContent = `<div class="img-placeholder">${isGenerating ? icon.sparkles(32) : icon.image(32)}</div>`
  } else {
    thumbContent = urls.map((url, i) =>
      `<img class="thumb-img${i === 0 ? ' thumb-active' : ''}" src="${url}" alt="" loading="lazy">`
    ).join('')
    if (urls.length > 1) {
      const dots = urls.map((_, i) => `<span class="thumb-dot${i === 0 ? ' active' : ''}"></span>`).join('')
      thumbContent += `<div class="thumb-dots">${dots}</div>`
    }
  }

  return `
    <div class="product-card${isGenerating ? ' generating' : ''}" data-sku="${p.sku_id}">
      <div class="product-thumb" data-img-count="${urls.length}">
        ${thumbContent}
        ${p.ai_image_count > 0 ? `<span class="ai-badge">${icon.sparkles(10)} ${p.ai_image_count}</span>` : ''}
        ${isGenerating ? `<div class="generating-overlay">${icon.sparkles(16)} Generating…</div>` : ''}
      </div>
      <div class="product-info">
        <div class="product-name">${p.marketing_name || p.sku_id}</div>
        <div class="product-sku mono">${p.sku_id}</div>
        <div class="product-meta">
          ${p.brand?.brand_name ? `<span class="tag tag-slate">${p.brand.brand_name}</span>` : ''}
          ${p.season ? `<span class="tag tag-blue">${p.season}</span>` : ''}
        </div>
        ${p.keywords?.length ? `<div class="product-keywords">${p.keywords.slice(0,3).map(k => `<span class="tag tag-dim">${k}</span>`).join('')}${p.keywords.length > 3 ? `<span class="tag tag-dim">+${p.keywords.length - 3}</span>` : ''}</div>` : ''}
        <div class="product-footer">
          <span class="status-badge status-${p.status}">${statusLabel(p.status)}</span>
          <span class="img-count">${icon.image(11)} ${p.original_image_count || 0}</span>
        </div>
      </div>
    </div>
  `
}

function productRow(p) {
  const kw = p.keywords?.slice(0, 3).map(k => `<span class="tag tag-dim" style="font-size:10px;">${k}</span>`).join('') || ''
  const thumb = p.thumbnail_url
    ? `<img src="${p.thumbnail_url}" alt="" style="width:40px;height:40px;object-fit:cover;border-radius:4px;">`
    : `<div style="width:40px;height:40px;border-radius:4px;background:var(--surface-2);display:flex;align-items:center;justify-content:center;">${icon.image(14)}</div>`
  return `
    <tr class="product-row" data-sku="${p.sku_id}">
      <td style="padding:8px 12px;">${thumb}</td>
      <td class="mono text-dim" style="padding:8px 12px;font-size:12px;">${p.sku_id}</td>
      <td style="padding:8px 12px;">
        <div style="font-weight:500;">${p.marketing_name || '—'}</div>
        ${kw ? `<div style="margin-top:3px;">${kw}</div>` : ''}
      </td>
      <td style="padding:8px 12px;">${p.brand?.brand_name || '—'}</td>
      <td style="padding:8px 12px;">${p.season || '—'}</td>
      <td style="padding:8px 12px;"><span class="status-badge status-${p.status}">${statusLabel(p.status)}</span></td>
      <td style="padding:8px 12px;text-align:right;">${p.ai_image_count || 0} AI / ${p.original_image_count || 0} orig</td>
    </tr>
  `
}

export async function render(container) {
  try { brands = await adminApi.brands() } catch {}
  try { [seasons, campaigns, departments] = await Promise.all([productsApi.seasons(), productsApi.campaigns(), productsApi.departments()]) } catch {}
  try {
    const res = await fetch('/api/admin/categories', { headers: { Authorization: `Bearer ${(await import('../auth.js')).getToken()}` } })
    if (res.ok) categories = await res.json()
  } catch {}

  function buildPage(products, total) {
    const totalPages = Math.ceil(total / filters.page_size)
    const hasFilters = filters.search || filters.season || filters.brand_id || filters.status ||
      filters.text_approval_date || filters.ingestion_date || filters.campaign_name || filters.department || filters.stock_level || filters.category_id

    container.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Products</h1>
          <p class="page-sub">${total} products</p>
        </div>
        <div class="header-actions">
          <button class="btn btn-secondary view-btn ${viewMode === 'grid' ? 'active' : ''}" data-view="grid">${icon.grid(14)}</button>
          <button class="btn btn-secondary view-btn ${viewMode === 'list' ? 'active' : ''}" data-view="list">${icon.list(14)}</button>
        </div>
      </div>

      <div class="filter-bar card">
        <div class="filter-grid">
          <div class="field">
            <label class="label">Import Date</label>
            <input type="date" id="f-ingestion-date" class="input" value="${filters.ingestion_date || ''}">
          </div>
          <div class="field">
            <label class="label">Approval Date</label>
            <input type="date" id="f-date" class="input" value="${filters.text_approval_date || ''}">
          </div>
          <div class="field">
            <label class="label">Season</label>
            <select id="f-season" class="input">
              <option value="">All seasons</option>
              ${seasons.map(s => `<option value="${s}" ${filters.season === s ? 'selected' : ''}>${s}</option>`).join('')}
            </select>
          </div>
          <div class="field">
            <label class="label">Brand</label>
            <select id="f-brand" class="input">
              <option value="">All brands</option>
              ${brands.map(b => `<option value="${b.id}" ${filters.brand_id === b.id ? 'selected' : ''}>${b.brand_name}</option>`).join('')}
            </select>
          </div>
          <div class="field">
            <label class="label">Retail Hierarchy</label>
            <select id="f-category" class="input">
              <option value="">All categories</option>
              ${categories.map(c => `<option value="${c.id}" ${filters.category_id === c.id ? 'selected' : ''}>${c.name}</option>`).join('')}
            </select>
          </div>
          <div class="field">
            <label class="label">Campaign</label>
            <select id="f-campaign" class="input">
              <option value="">All campaigns</option>
              ${campaigns.map(c => `<option value="${c}" ${filters.campaign_name === c ? 'selected' : ''}>${c}</option>`).join('')}
            </select>
          </div>
          <div class="field">
            <label class="label">Department</label>
            <select id="f-department" class="input">
              <option value="">All departments</option>
              ${departments.map(d => `<option value="${d}" ${filters.department === d ? 'selected' : ''}>${d}</option>`).join('')}
            </select>
          </div>
          <div class="field">
            <label class="label">Stock Level (HKI)</label>
            <select id="f-stock" class="input">
              <option value="" ${!filters.stock_level ? 'selected' : ''}>All levels</option>
              <option value="none" ${filters.stock_level === 'none' ? 'selected' : ''}>None (0)</option>
              <option value="low"  ${filters.stock_level === 'low'  ? 'selected' : ''}>Low (1–19)</option>
              <option value="high" ${filters.stock_level === 'high' ? 'selected' : ''}>High (20+)</option>
            </select>
          </div>
          <div class="field">
            <label class="label">Status</label>
            <select id="f-status" class="input">
              ${STATUSES.map(s => `<option value="${s.value}" ${filters.status === s.value ? 'selected' : ''}>${s.label}</option>`).join('')}
            </select>
          </div>
          <div class="field" style="flex:2;">
            <label class="label">Search SKU / Name</label>
            <input type="text" id="f-search" class="input" placeholder="Search..." value="${filters.search || ''}">
          </div>
          ${hasFilters ? `<div class="field" style="align-self:flex-end;"><button id="btn-reset" class="btn btn-secondary">Reset</button></div>` : ''}
        </div>
      </div>

      <div id="product-grid">
        ${viewMode === 'grid'
          ? `<div class="product-grid">${products.map(productCard).join('') || '<p class="text-dim p-8">No products found.</p>'}</div>`
          : `<div class="card" style="overflow:auto;">
               <table class="data-table">
                 <thead><tr>
                   <th style="width:56px;"></th><th>SKU</th><th>Name</th><th>Brand</th><th>Season</th><th>Status</th><th style="text-align:right;">Images</th>
                 </tr></thead>
                 <tbody>${products.map(productRow).join('') || '<tr><td colspan="6" class="text-dim" style="padding:20px;text-align:center;">No products found.</td></tr>'}</tbody>
               </table>
             </div>`
        }
      </div>

      ${totalPages > 1 ? `
        <div class="pagination">
          <button class="btn btn-secondary" id="btn-prev" ${filters.page <= 1 ? 'disabled' : ''}>← Previous</button>
          <span class="text-dim">Page ${filters.page} of ${totalPages}</span>
          <button class="btn btn-secondary" id="btn-next" ${filters.page >= totalPages ? 'disabled' : ''}>Next →</button>
        </div>
      ` : ''}
    `

    // View toggle
    container.querySelectorAll('.view-btn').forEach(b => b.addEventListener('click', () => {
      viewMode = b.dataset.view
      loadProducts()
    }))

    // Filters
    const setFilter = (key, val) => { filters[key] = val; filters.page = 1; loadProducts() }
    container.querySelector('#f-ingestion-date')?.addEventListener('change', e => setFilter('ingestion_date', e.target.value))
    container.querySelector('#f-date')?.addEventListener('change', e => setFilter('text_approval_date', e.target.value))
    container.querySelector('#f-season')?.addEventListener('change', e => setFilter('season', e.target.value))
    container.querySelector('#f-brand')?.addEventListener('change', e => setFilter('brand_id', e.target.value))
    container.querySelector('#f-category')?.addEventListener('change', e => setFilter('category_id', e.target.value))
    container.querySelector('#f-campaign')?.addEventListener('change', e => setFilter('campaign_name', e.target.value))
    container.querySelector('#f-department')?.addEventListener('change', e => setFilter('department', e.target.value))
    container.querySelector('#f-stock')?.addEventListener('change', e => setFilter('stock_level', e.target.value))
    container.querySelector('#f-status')?.addEventListener('change', e => setFilter('status', e.target.value))

    let searchTimer
    container.querySelector('#f-search')?.addEventListener('input', e => {
      clearTimeout(searchTimer)
      searchTimer = setTimeout(() => setFilter('search', e.target.value), 350)
    })
    container.querySelector('#btn-reset')?.addEventListener('click', () => {
      filters = { search: '', season: '', brand_id: '', status: '', text_approval_date: '', ingestion_date: '', campaign_name: '', department: '', stock_level: '', category_id: '', page: 1, page_size: 30 }
      loadProducts()
    })

    // Navigate to product detail
    container.querySelectorAll('[data-sku]').forEach(el => {
      el.addEventListener('click', () => navigate(`/products/${el.dataset.sku}`))
    })

    // Hover image cycling — auto-advance through all images while cursor is on card
    container.querySelectorAll('.product-thumb[data-img-count]').forEach(thumb => {
      const count = parseInt(thumb.dataset.imgCount)
      if (count <= 1) return
      const imgs = thumb.querySelectorAll('.thumb-img')
      const dots = thumb.querySelectorAll('.thumb-dot')
      let cur = 0
      let timer = null
      const show = (idx) => {
        imgs[cur].classList.remove('thumb-active')
        dots[cur]?.classList.remove('active')
        cur = idx
        imgs[cur].classList.add('thumb-active')
        dots[cur]?.classList.add('active')
      }
      thumb.addEventListener('mouseenter', () => {
        timer = setInterval(() => show((cur + 1) % count), 700)
      })
      thumb.addEventListener('mouseleave', () => {
        clearInterval(timer)
        timer = null
        show(0)
      })
    })

    // Pagination
    container.querySelector('#btn-prev')?.addEventListener('click', () => { filters.page--; loadProducts() })
    container.querySelector('#btn-next')?.addEventListener('click', () => { filters.page++; loadProducts() })
  }

  async function loadProducts(silent = false) {
    if (!silent) container.innerHTML = `<div class="loading">${icon.loader(24)}<span>Loading products...</span></div>`
    try {
      const data = await productsApi.list(filters)
      const items = data.items || data
      buildPage(items, data.total || items.length)

      // Always poll so changes made by other users (AI_READY, etc.) are visible in real-time.
      // Poll faster (5s) while something is generating, slower (15s) otherwise.
      const hasGenerating = items.some(p => p.status === 'AI_GENERATING')
      const interval = hasGenerating ? 5000 : 15000
      if (!pollTimer) {
        pollTimer = setInterval(() => loadProducts(true), interval)
      }
    } catch (err) {
      if (silent) {
        // During background polling don't wipe the existing grid — just show a brief toast
        toast.error('Could not refresh product list')
      } else {
        toast.error('Failed to load products')
        container.innerHTML = `<div class="error-state">${icon.alert(16)} Failed to load products</div>`
      }
    }
  }

  loadProducts()
  return () => { if (pollTimer) { clearInterval(pollTimer); pollTimer = null } }
}
