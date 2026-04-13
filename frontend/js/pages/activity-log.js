import { adminApi } from '../api.js'
import { toast } from '../toast.js'
import { icon } from '../icons.js'
import { navigate } from '../router.js'
import { getUser } from '../auth.js'

// Human-readable labels and colours per action type
const ACTION_META = {
  AI_GENERATED:         { label: 'AI Generated',        color: 'purple' },
  AI_REGENERATED:       { label: 'AI Regenerated',       color: 'purple' },
  IMAGE_APPROVED:       { label: 'Image Approved',       color: 'green'  },
  IMAGE_RECALLED:       { label: 'Image Recalled',       color: 'orange' },
  IMAGE_REJECTED:       { label: 'Image Rejected',       color: 'red'    },
  IMAGE_REORDERED:      { label: 'Image Reordered',      color: 'blue'   },
  PROMPT_EDITED:        { label: 'Prompt Edited',        color: 'teal'   },
  PROMPT_LIBRARY_UPDATED: { label: 'Prompt Library Updated', color: 'teal' },
  PRODUCT_SELECTED:     { label: 'Product Selected',     color: 'green'  },
  PRODUCT_DESELECTED:   { label: 'Product Deselected',   color: 'slate'  },
  USER_CREATED:         { label: 'User Created',         color: 'slate'  },
  USER_DEACTIVATED:     { label: 'User Deactivated',     color: 'red'    },
}

const ALL_ACTIONS = Object.keys(ACTION_META)

let filters = { action: '', sku_id: '', user_id: '', date_from: '', date_to: '', limit: 200 }
let allUsers = []

function formatDateTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('fi-FI', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function actionBadge(action) {
  const meta = ACTION_META[action] || { label: action.replace(/_/g, ' '), color: 'slate' }
  return `<span class="activity-badge activity-badge-${meta.color}">${meta.label}</span>`
}

function payloadSummary(action, payload) {
  if (!payload) return ''
  const parts = []
  if (payload.session_id)           parts.push(`Session: ${payload.session_id.slice(0, 8)}…`)
  if (payload.new_prompt_preview)   parts.push(`"${payload.new_prompt_preview.slice(0, 80)}${payload.new_prompt_preview.length > 80 ? '…' : ''}"`)
  if (payload.prompt_type)          parts.push(`Type: ${payload.prompt_type}`)
  if (payload.version !== undefined) parts.push(`v${payload.version}`)
  if (payload.key)                  parts.push(`Key: ${payload.key.split('/').pop()}`)
  if (payload.keys?.length)         parts.push(`${payload.keys.length} image(s)`)
  if (payload.reason)               parts.push(`Reason: ${payload.reason}`)
  if (payload.email)                parts.push(payload.email)
  if (payload.role)                 parts.push(`Role: ${payload.role}`)
  if (payload.target_user)          parts.push(`User: ${payload.target_user.slice(0, 8)}…`)
  return parts.join(' · ')
}

function activityRow(entry) {
  const user = entry.user
  const userName = user?.full_name || user?.email || 'System'
  const detail = payloadSummary(entry.action, entry.payload)

  return `
    <tr class="activity-row">
      <td class="activity-time mono">${formatDateTime(entry.occurred_at)}</td>
      <td class="activity-user">
        <span class="user-chip">${icon.user(11)} ${userName}</span>
      </td>
      <td class="activity-action">${actionBadge(entry.action)}</td>
      <td class="activity-sku">
        ${entry.sku_id
          ? `<a class="sku-link mono" data-sku="${entry.sku_id}">${entry.sku_id}</a>`
          : '<span class="text-dim">—</span>'}
      </td>
      <td class="activity-detail text-dim">${detail}</td>
    </tr>
  `
}

export async function render(container) {
  const currentUser = getUser()

  // Load users list for filter dropdown (only available to admins — gracefully degrade)
  try {
    allUsers = await adminApi.users()
  } catch {
    allUsers = []
  }

  async function loadLog(silent = false) {
    if (!silent) {
      container.innerHTML = `<div class="loading">${icon.loader(24)}<span>Loading activity log…</span></div>`
    }

    const params = {}
    if (filters.action)    params.action    = filters.action
    if (filters.sku_id)    params.sku_id    = filters.sku_id.trim()
    if (filters.user_id)   params.user_id   = filters.user_id
    if (filters.date_from) params.date_from = filters.date_from
    if (filters.date_to)   params.date_to   = filters.date_to + (filters.date_to ? 'T23:59:59' : '')
    params.limit = filters.limit

    let entries = []
    try {
      entries = await adminApi.auditTrail(params)
    } catch (err) {
      toast.error('Failed to load activity log')
      container.innerHTML = `<div class="error-state">${icon.alert(16)} Failed to load activity log</div>`
      return
    }

    buildPage(entries)
  }

  function buildPage(entries) {
    const hasFilters = filters.action || filters.sku_id || filters.user_id || filters.date_from || filters.date_to

    container.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Activity Log</h1>
          <p class="page-sub">${entries.length} events</p>
        </div>
        <button id="btn-refresh" class="btn btn-secondary">${icon.recall(14)} Refresh</button>
      </div>

      <div class="filter-bar card" style="margin-bottom:16px;">
        <div class="filter-grid">
          <div class="field">
            <label class="label">Action</label>
            <select id="f-action" class="input">
              <option value="">All actions</option>
              ${ALL_ACTIONS.map(a => {
                const meta = ACTION_META[a]
                return `<option value="${a}" ${filters.action === a ? 'selected' : ''}>${meta.label}</option>`
              }).join('')}
            </select>
          </div>
          ${allUsers.length > 0 ? `
          <div class="field">
            <label class="label">User</label>
            <select id="f-user" class="input">
              <option value="">All users</option>
              ${allUsers.map(u => `<option value="${u.id}" ${filters.user_id === u.id ? 'selected' : ''}>${u.full_name || u.email}</option>`).join('')}
            </select>
          </div>
          ` : ''}
          <div class="field">
            <label class="label">SKU</label>
            <input type="text" id="f-sku" class="input" placeholder="SKU ID…" value="${filters.sku_id}">
          </div>
          <div class="field">
            <label class="label">From</label>
            <input type="date" id="f-from" class="input" value="${filters.date_from}">
          </div>
          <div class="field">
            <label class="label">To</label>
            <input type="date" id="f-to" class="input" value="${filters.date_to}">
          </div>
          <div class="field">
            <label class="label">Show</label>
            <select id="f-limit" class="input">
              <option value="100"  ${filters.limit === 100  ? 'selected' : ''}>Last 100</option>
              <option value="200"  ${filters.limit === 200  ? 'selected' : ''}>Last 200</option>
              <option value="500"  ${filters.limit === 500  ? 'selected' : ''}>Last 500</option>
              <option value="1000" ${filters.limit === 1000 ? 'selected' : ''}>Last 1000</option>
            </select>
          </div>
          ${hasFilters ? `<div class="field" style="align-self:flex-end;"><button id="btn-reset" class="btn btn-secondary">Reset</button></div>` : ''}
        </div>
      </div>

      ${entries.length === 0
        ? `<div class="card" style="padding:40px;text-align:center;color:var(--text-dim);">${icon.history(32)}<p style="margin-top:12px;">No activity found.</p></div>`
        : `<div class="card" style="overflow:auto;">
             <table class="data-table activity-table">
               <thead><tr>
                 <th style="width:160px;">Time</th>
                 <th style="width:150px;">User</th>
                 <th style="width:180px;">Action</th>
                 <th style="width:130px;">Product SKU</th>
                 <th>Details</th>
               </tr></thead>
               <tbody>${entries.map(activityRow).join('')}</tbody>
             </table>
           </div>`
      }
    `

    // Filter events
    container.querySelector('#f-action')?.addEventListener('change', e => { filters.action = e.target.value; loadLog() })
    container.querySelector('#f-user')?.addEventListener('change', e => { filters.user_id = e.target.value; loadLog() })
    container.querySelector('#f-limit')?.addEventListener('change', e => { filters.limit = parseInt(e.target.value); loadLog() })

    let skuTimer
    container.querySelector('#f-sku')?.addEventListener('input', e => {
      clearTimeout(skuTimer)
      skuTimer = setTimeout(() => { filters.sku_id = e.target.value; loadLog() }, 400)
    })

    container.querySelector('#f-from')?.addEventListener('change', e => { filters.date_from = e.target.value; loadLog() })
    container.querySelector('#f-to')?.addEventListener('change', e => { filters.date_to = e.target.value; loadLog() })

    container.querySelector('#btn-reset')?.addEventListener('click', () => {
      filters = { action: '', sku_id: '', user_id: '', date_from: '', date_to: '', limit: 200 }
      loadLog()
    })

    container.querySelector('#btn-refresh')?.addEventListener('click', () => loadLog())

    // Navigate to product detail on SKU click
    container.querySelectorAll('.sku-link[data-sku]').forEach(el => {
      el.addEventListener('click', e => {
        e.preventDefault()
        navigate(`/products/${el.dataset.sku}`)
      })
    })
  }

  loadLog()
}
