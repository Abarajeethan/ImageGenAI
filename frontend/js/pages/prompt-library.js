import { promptsApi, adminApi } from '../api.js'
import { toast } from '../toast.js'
import { icon } from '../icons.js'
import { getUser } from '../auth.js'

export async function render(container) {
  const user = getUser()
  const isAdmin = user?.role === 'ADMIN'
  let library = []
  let brands = []
  let systemPrompt = null
  let editingId = null
  let editDraft = ''
  let showNewForm = false
  let newForm = { prompt_type: 'GENERAL', brand_id: '', department: '', prompt_text: '' }
  let departments = []

  async function load() {
    try {
      const { productsApi } = await import('../api.js')
      ;[library, brands, departments] = await Promise.all([promptsApi.listLibrary(), adminApi.brands(), productsApi.departments()])
    } catch { toast.error('Failed to load prompt library') }
    try {
      const sp = await promptsApi.getSystemPrompt()
      systemPrompt = sp.prompt_text
    } catch {}
    renderPage()
  }

  function renderPage() {
    const general = library.filter(p => p.prompt_type === 'GENERAL' && p.is_active)
    const brand   = library.filter(p => p.prompt_type === 'BRAND'   && p.is_active)

    container.innerHTML = `
      <div class="page-content">
        <div class="page-header">
          <h1 class="page-title">Prompt Library</h1>
          ${isAdmin ? `<button id="btn-new" class="btn btn-primary">${icon.plus(14)} New Prompt</button>` : ''}
        </div>

        ${showNewForm && isAdmin ? `
          <div class="card" style="padding:20px;margin-bottom:16px;">
            <div class="section-title" style="margin-bottom:12px;">New Prompt</div>
            <div class="filter-grid" style="grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;">
              <div class="field">
                <label class="label">Type</label>
                <select id="nf-type" class="input">
                  <option value="GENERAL" ${newForm.prompt_type === 'GENERAL' ? 'selected' : ''}>General</option>
                  <option value="BRAND"   ${newForm.prompt_type === 'BRAND'   ? 'selected' : ''}>Brand-Specific</option>
                </select>
              </div>
              <div class="field" id="nf-brand-field" style="${newForm.prompt_type === 'BRAND' ? '' : 'visibility:hidden;'}">
                <label class="label">Brand Name</label>
                <input id="nf-brand-name" type="text" class="input" placeholder="e.g. Nike"
                  list="brand-suggestions" value="${newForm.brand_name || ''}">
                <datalist id="brand-suggestions">
                  ${brands.map(b => `<option value="${b.brand_name}">`).join('')}
                </datalist>
              </div>
              <div class="field" id="nf-dept-field" style="${newForm.prompt_type === 'BRAND' ? '' : 'visibility:hidden;'}">
                <label class="label">Department (optional)</label>
                <select id="nf-dept" class="input">
                  <option value="">All departments</option>
                  ${departments.map(d => `<option value="${d}" ${newForm.department === d ? 'selected' : ''}>${d}</option>`).join('')}
                </select>
              </div>
            </div>
            <div class="field" style="margin-top:12px;">
              <label class="label">Prompt Text</label>
              <textarea id="nf-text" class="input" rows="5" placeholder="Describe how AI should photograph these products…">${newForm.prompt_text}</textarea>
            </div>
            <div class="field" style="margin-top:8px;">
              <label class="label">Description (optional)</label>
              <input id="nf-desc" type="text" class="input" placeholder="Brief note about this prompt…">
            </div>
            <div class="prompt-actions" style="margin-top:12px;">
              <button id="btn-save-new" class="btn btn-primary">${icon.save(12)} Save</button>
              <button id="btn-cancel-new" class="btn btn-secondary">Cancel</button>
            </div>
          </div>
        ` : ''}

        <!-- AI System Prompt -->
        <div class="section-title" style="margin-bottom:8px;">AI Analysis System Prompt</div>
        <div class="card" style="padding:16px;margin-bottom:20px;">
          <div class="flex-row gap-2" style="margin-bottom:8px;">
            <span class="tag tag-purple">SYSTEM</span>
            <span class="text-dim" style="font-size:12px;">Used by Gemini to analyse product images and generate 3 prompt options</span>
          </div>
          ${systemPrompt
            ? '<pre class="prompt-text" style="font-size:12px;white-space:pre-wrap;word-break:break-word;max-height:300px;overflow-y:auto;">' + systemPrompt + '</pre>'
            : '<p class="text-dim" style="font-size:13px;">Loading...</p>'
          }
        </div>

        <!-- General prompts -->
        <div class="section-title" style="margin-bottom:8px;">General Prompts</div>
        ${general.length === 0 ? `<p class="text-dim" style="margin-bottom:16px;">No general prompts.</p>` : ''}
        ${general.map(p => promptCard(p)).join('')}

        <!-- Brand prompts -->
        <div class="section-title" style="margin:16px 0 8px;">Brand-Specific Prompts</div>
        ${brand.length === 0 ? `<p class="text-dim">No brand prompts.</p>` : ''}
        ${brand.map(p => promptCard(p)).join('')}
      </div>
    `

    // New form controls
    container.querySelector('#btn-new')?.addEventListener('click', () => { showNewForm = true; renderPage() })
    container.querySelector('#btn-cancel-new')?.addEventListener('click', () => { showNewForm = false; renderPage() })
    container.querySelector('#nf-type')?.addEventListener('change', e => {
      newForm.prompt_type = e.target.value
      const isBrand = e.target.value === 'BRAND'
      const bf = container.querySelector('#nf-brand-field')
      const df = container.querySelector('#nf-dept-field')
      if (bf) bf.style.visibility = isBrand ? 'visible' : 'hidden'
      if (df) df.style.visibility = isBrand ? 'visible' : 'hidden'
    })
    container.querySelector('#nf-brand-name')?.addEventListener('input', e => { newForm.brand_name = e.target.value })
    container.querySelector('#nf-dept')?.addEventListener('change', e => { newForm.department = e.target.value })
    container.querySelector('#nf-text')?.addEventListener('input', e => { newForm.prompt_text = e.target.value })
    container.querySelector('#btn-save-new')?.addEventListener('click', async () => {
      const text = container.querySelector('#nf-text').value.trim()
      const desc = container.querySelector('#nf-desc').value.trim()
      if (!text) { toast.error('Prompt text is required'); return }

      let brandId = null
      if (newForm.prompt_type === 'BRAND') {
        const brandName = (container.querySelector('#nf-brand-name')?.value || '').trim()
        if (!brandName) { toast.error('Brand name is required for Brand prompts'); return }
        // Find existing brand by name
        const match = brands.find(b => b.brand_name.toLowerCase() === brandName.toLowerCase())
        if (match) {
          brandId = match.id
        } else {
          toast.error(`Brand "${brandName}" not found. Import the Excel first so brands are created.`)
          return
        }
      }

      try {
        const dept = (container.querySelector('#nf-dept')?.value || '').trim() || null
        await promptsApi.createLibrary({ prompt_type: newForm.prompt_type, brand_id: brandId, department: dept, prompt_text: text, description: desc || null })
        toast.success('Prompt saved')
        showNewForm = false
        newForm = { prompt_type: 'GENERAL', brand_id: '', brand_name: '', department: '', prompt_text: '' }
        await load()
      } catch (err) { toast.error(err.message || 'Failed') }
    })

    // Edit controls
    container.querySelectorAll('.btn-edit-prompt').forEach(b => b.addEventListener('click', () => {
      editingId = b.dataset.id
      editDraft = library.find(p => p.id === editingId)?.prompt_text || ''
      renderPage()
    }))
    container.querySelectorAll('.btn-cancel-edit').forEach(b => b.addEventListener('click', () => { editingId = null; renderPage() }))
    container.querySelectorAll('.edit-textarea').forEach(ta => ta.addEventListener('input', e => { editDraft = e.target.value }))
    container.querySelectorAll('.btn-save-edit').forEach(b => b.addEventListener('click', async () => {
      try {
        await promptsApi.updateLibrary(b.dataset.id, { prompt_text: editDraft })
        toast.success('Prompt updated')
        editingId = null
        await load()
      } catch (err) { toast.error(err.message || 'Failed') }
    }))
  }

  function promptCard(p) {
    const brand = brands.find(b => b.id === p.brand_id)
    const isEditing = editingId === p.id
    return `
      <div class="card" style="padding:16px;margin-bottom:12px;">
        <div class="flex-row gap-2" style="margin-bottom:8px;">
          <span class="tag tag-blue">${p.prompt_type}</span>
          ${brand ? `<span class="tag tag-slate">${brand.brand_name}</span>` : ''}
          ${p.department ? `<span class="tag tag-amber">${p.department}</span>` : ''}
          <span class="tag tag-slate">v${p.version}</span>
          ${p.description ? `<span class="text-dim" style="font-size:12px;">${p.description}</span>` : ''}
          ${isAdmin ? `<button class="btn btn-secondary btn-sm btn-edit-prompt" data-id="${p.id}" style="margin-left:auto;">${icon.edit(12)} Edit</button>` : ''}
        </div>
        ${isEditing ? `
          <textarea class="input edit-textarea" rows="5" data-id="${p.id}">${editDraft}</textarea>
          <div class="prompt-actions" style="margin-top:8px;">
            <button class="btn btn-primary btn-sm btn-save-edit" data-id="${p.id}">${icon.save(12)} Save</button>
            <button class="btn btn-secondary btn-sm btn-cancel-edit">Cancel</button>
          </div>
        ` : `
          <div class="prompt-text" style="font-size:13px;">${p.prompt_text}</div>
          <div class="prompt-meta text-dim" style="margin-top:8px;">
            ${p.created_by ? `by ${p.created_by.full_name}` : ''} · ${new Date(p.updated_at || p.created_at).toLocaleDateString()}
          </div>
        `}
      </div>
    `
  }

  container.innerHTML = `<div class="loading">${icon.loader(24)}<span>Loading...</span></div>`
  await load()
}
