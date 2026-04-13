import { productsApi, promptsApi, approvalsApi } from '../api.js'
import { toast } from '../toast.js'
import { icon } from '../icons.js'
import { navigate } from '../router.js'

// ──────────────────────────────────────────────────────────────────────────────

function infoRow(ico, label, value) {
  if (value == null || value === '' || value === undefined) return ''
  return `
    <div class="info-row">
      <span class="info-icon">${ico}</span>
      <div>
        <div class="info-label">${label}</div>
        <div class="info-value">${value}</div>
      </div>
    </div>
  `
}

// ─── AI Generation Progress Modal ─────────────────────────────────────────────
function showGenerationModal() {
  const existing = document.getElementById('ai-gen-modal')
  if (existing) return existing

  const modal = document.createElement('div')
  modal.id = 'ai-gen-modal'
  modal.innerHTML = `
    <style>
      #ai-gen-modal .gen-overlay{position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:10000;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(6px);}
      #ai-gen-modal .gen-box{background:var(--surface-1,#1e1e2e);border:1px solid var(--border,#333);border-radius:18px;padding:40px 48px;min-width:360px;text-align:center;box-shadow:0 32px 80px rgba(0,0,0,.6);}
      #ai-gen-modal .gen-emoji{font-size:52px;margin-bottom:16px;animation:gen-bounce 1.2s ease-in-out infinite;}
      #ai-gen-modal .gen-title{font-size:18px;font-weight:700;margin-bottom:8px;color:var(--text,#eee);}
      #ai-gen-modal .gen-sub{font-size:13px;color:var(--text-dim,#888);line-height:1.6;}
      #ai-gen-modal .gen-dots span{display:inline-block;animation:gen-dot 1.4s infinite;font-size:22px;}
      #ai-gen-modal .gen-dots span:nth-child(2){animation-delay:.2s;}
      #ai-gen-modal .gen-dots span:nth-child(3){animation-delay:.4s;}
      #ai-gen-modal .gen-bar{height:4px;border-radius:2px;background:var(--surface-2,#252535);margin-top:24px;overflow:hidden;}
      #ai-gen-modal .gen-bar-fill{height:100%;border-radius:2px;background:linear-gradient(90deg,#6366f1,#a855f7);animation:gen-slide 2s ease-in-out infinite;}
      #ai-gen-modal .gen-error{margin-top:16px;padding:12px;background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.3);border-radius:8px;font-size:12px;color:#f87171;text-align:left;word-break:break-word;max-height:120px;overflow:auto;font-family:monospace;}
      #ai-gen-modal .gen-error-title{font-weight:700;margin-bottom:6px;font-family:sans-serif;font-size:13px;}
      #ai-gen-modal .gen-close-btn{margin-top:20px;display:none;}
      @keyframes gen-bounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}
      @keyframes gen-dot{0%,80%,100%{opacity:.2}40%{opacity:1}}
      @keyframes gen-slide{0%{transform:translateX(-100%)}100%{transform:translateX(200%)}}
    </style>
    <div class="gen-overlay">
      <div class="gen-box">
        <div class="gen-emoji" id="gen-emoji">✨</div>
        <div class="gen-title" id="gen-title">Generating AI Prompt…</div>
        <div class="gen-sub" id="gen-sub">Analysing product and crafting the perfect prompt</div>
        <div class="gen-dots"><span>·</span><span>·</span><span>·</span></div>
        <div class="gen-bar"><div class="gen-bar-fill"></div></div>
        <button class="btn btn-secondary gen-close-btn" id="gen-close-btn">Close</button>
      </div>
    </div>
  `
  document.body.appendChild(modal)
  modal.querySelector('#gen-close-btn').addEventListener('click', () => modal.remove())
  return modal
}

function updateGenerationModal(stage) {
  const modal = document.getElementById('ai-gen-modal')
  if (!modal) return
  const emoji = modal.querySelector('#gen-emoji')
  const title = modal.querySelector('#gen-title')
  const sub   = modal.querySelector('#gen-sub')
  if (stage === 'prompt') {
    emoji.textContent = '✨'; title.textContent = 'Generating AI Prompt…'
    sub.textContent = 'Analysing product and crafting the perfect prompt'
  } else if (stage === 'image') {
    emoji.textContent = '🎨'; title.textContent = 'Generating AI Image…'
    sub.textContent = 'Creating a professional fashion photo — this may take 30–60 seconds'
  } else if (stage === 'done') {
    emoji.textContent = '🎉'; title.textContent = 'Image Ready!'
    sub.textContent = 'Your AI image has been generated successfully'
    modal.querySelector('.gen-dots').style.display = 'none'
    modal.querySelector('.gen-bar').style.display = 'none'
    setTimeout(() => modal.remove(), 1800)
  } else if (stage === 'error') {
    emoji.textContent = '❌'; title.textContent = 'Generation Failed'
    modal.querySelector('.gen-dots').style.display = 'none'
    modal.querySelector('.gen-bar').style.display = 'none'
    modal.querySelector('#gen-close-btn').style.display = 'inline-block'
  }
}

function showGenerationError(errorText) {
  const modal = document.getElementById('ai-gen-modal')
  if (!modal) return
  const box = modal.querySelector('.gen-box')
  let errEl = box.querySelector('.gen-error')
  if (!errEl) {
    errEl = document.createElement('div')
    errEl.className = 'gen-error'
    box.appendChild(errEl)
  }
  errEl.innerHTML = `<div class="gen-error-title">Error Details</div>${errorText}`
}

function dismissGenerationModal() {
  document.getElementById('ai-gen-modal')?.remove()
}

// ──────────────────────────────────────────────────────────────────────────────

function statusLabel(s) { return s.replace(/_/g, ' ') }

function stockLabel(val, thresholdHigh = 20) {
  if (val == null) return null
  if (val === 0) return 'None'
  if (val < thresholdHigh) return 'Low'
  return 'High'
}

let pollTimer = null

export async function render(container, { sku }) {
  let product = null
  let promptHistory = null
  let showHistory = false
  let editingPrompt = false
  let promptDraft = ''
  let generatingAIPrompt = false
  let aiAnalysis = null
  let generatedPrompts = null

  let sortable = null

  async function loadProduct() {
    try {
      product = await productsApi.get(sku)
      renderPage()

      if (product.status === 'AI_GENERATING') {
        updateGenerationModal('image')
        if (!pollTimer) pollTimer = setInterval(async () => {
          try {
            product = await productsApi.get(sku)
            renderPage()
            if (product.status !== 'AI_GENERATING') {
              clearInterval(pollTimer); pollTimer = null
              if (product.status === 'AI_FAILED') {
                updateGenerationModal('error')
                showGenerationError(product.generation_error || 'Unknown error — check backend logs')
              } else {
                updateGenerationModal('done')
              }
            }
          } catch {}
        }, 3000)
      } else if (product.status === 'AI_FAILED') {
        dismissGenerationModal()
      } else {
        clearInterval(pollTimer); pollTimer = null
        dismissGenerationModal()
      }
    } catch {
      container.innerHTML = `<div class="error-state">${icon.alert(16)} Failed to load product</div>`
    }
  }

  function imageCard(img, idx, type = 'ORIGINAL') {
    const isApproved = img.status === 'APPROVED'
    const isRecalled = img.status === 'RECALLED'
    const isAI = type === 'AI'
    const displayUrl = img.url || ''

    return `
      <div class="img-card ${isAI ? 'img-ai' : ''} ${isRecalled ? 'img-recalled' : ''}" data-key="${img.key || ''}">
        <div class="img-thumb img-open" data-url="${displayUrl}" data-idx="${idx}" data-type="${type}">
          ${displayUrl
            ? `<img src="${displayUrl}" alt="" loading="lazy">`
            : `<div class="img-placeholder">${icon.image(24)}</div>`}
          <div class="img-zoom-hint">${icon.expand(20)}</div>
          <span class="img-sort">#${idx + 1}</span>
          ${isAI ? `<span class="img-ai-badge">${icon.sparkles(10)} AI</span>` : ''}
          ${isApproved ? `<span class="img-approved-badge">${icon.check(10)}</span>` : ''}
          ${isAI && !isRecalled ? `<span class="img-drag-handle">${icon.grip(14)}</span>` : ''}
          ${isRecalled ? `<div class="img-recalled-diagonal">RECALLED</div>` : ''}
        </div>
        ${isAI ? `
          <div class="img-actions">
            ${isRecalled ? `
              <span class="img-recalled-label">Recalled</span>
            ` : isApproved ? `
              <button class="img-action-btn img-action-recall" data-key="${img.key}" title="Recall this image" style="font-size:10px;">
                ${icon.recall(12)} Recall
              </button>
            ` : `
              <button class="img-action-btn img-action-approve" data-key="${img.key}" title="Approve">
                ${icon.check(14)}
              </button>
              <button class="img-action-btn img-action-retry" data-key="${img.key}" title="Retry">
                ${icon.recall(14)}
              </button>
              <button class="img-action-btn img-action-reject" data-key="${img.key}" title="Reject">
                ${icon.xCircle(14)}
              </button>
            `}
          </div>
        ` : ''}
      </div>
    `
  }

  function renderPage() {
    const orig = product.images?.original || []
    const ai   = product.images?.ai || []
    const pendingAI  = ai.filter(i => i.status === 'PENDING')
    const approvedAI = ai.filter(i => i.status === 'APPROVED')

    container.innerHTML = `
      <style>
        .img-recalled-diagonal{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%) rotate(-30deg);background:rgba(239,68,68,.85);color:#fff;font-size:11px;font-weight:700;padding:4px 20px;white-space:nowrap;letter-spacing:.05em;border-radius:3px;}
        .img-card.img-recalled .img-thumb{opacity:.6;}
        .img-recalled-label{font-size:11px;color:var(--text-dim,#888);padding:4px 6px;}
      </style>
      <div class="detail-layout">

        <!-- Header -->
        <div class="detail-header">
          <button class="btn-icon" id="btn-back">${icon.arrowLeft(16)}</button>
          <div class="detail-title-block">
            <div class="flex-row gap-2">
              <h1 class="detail-title">${product.marketing_name || product.sku_id}</h1>
              <span class="status-badge status-${product.status}">${statusLabel(product.status)}</span>
              ${product.locked_by ? `<span class="tag tag-amber">${icon.lock(10)} ${product.locked_by.full_name}</span>` : ''}
            </div>
            <div class="detail-sku mono">${product.sku_id}</div>
          </div>
          <div class="header-actions">
            ${product.status === 'AI_GENERATING' ? `
              <span class="generating-indicator">${icon.loader(13)}<span> Generating AI images...</span></span>
            ` : ''}
            ${pendingAI.length > 0 ? `
              <button id="btn-approve-all" class="btn btn-success">
                ${icon.check(13)} Approve All AI (${pendingAI.length})
              </button>
            ` : ''}
          </div>
        </div>

        <!-- Body -->
        <div class="detail-body">

          <!-- Left sidebar -->
          <aside class="detail-sidebar">
            <div class="card detail-card">
              <div class="section-title">${icon.package(11)} Product Information</div>
              ${infoRow(icon.tag(13),       'Brand',            product.brand?.brand_name)}
              ${infoRow(icon.layers(13),    'Retail Hierarchy', product.category?.hierarchy || product.category?.name)}
              ${infoRow(icon.calendar(13),  'Season',           product.season)}
              ${infoRow(icon.megaphone(13), 'Campaign',         product.campaign_name)}
              ${infoRow(icon.image(13),     'Colour',           product.colour)}
              ${infoRow(icon.list(13),      'Size',             product.size)}
              ${infoRow(icon.tag(13),       'Department',       product.department)}
              ${infoRow(icon.warehouse(13), 'DC Stock',         stockLabel(product.dc_stock, 25))}
              ${infoRow(icon.store(13),     'Helsinki Stock',   stockLabel(product.hki_stock, 20))}
            </div>

            ${product.sibling_skus?.length ? `
              <div class="card detail-card">
                <div class="section-title">${icon.layers(11)} Sibling SKUs (${product.sibling_skus.length})</div>
                <div class="tag-group" style="margin-top:6px;">
                  ${product.sibling_skus.map(s => `<span class="tag tag-slate mono" style="cursor:pointer;" data-sibling="${s}">${s}</span>`).join('')}
                </div>
              </div>
            ` : ''}

            ${product.description ? `
              <div class="card detail-card">
                <div class="section-title">Description</div>
                <p class="text-dim" style="font-size:12px;line-height:1.65;">${product.description}</p>
              </div>
            ` : ''}

            ${(product.ai_description || product.ai_keywords?.length || product.ai_suggested_category) ? `
              <div class="card detail-card" style="border:1px solid rgba(99,102,241,0.25);">
                <div class="section-title" style="color:var(--purple,#7c3aed);">${icon.sparkles(11)} AI Generated</div>
                ${product.ai_suggested_category ? `
                  <div style="margin-top:8px;">
                    <div class="info-label" style="font-size:10px;font-weight:600;color:var(--text-dim);text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px;">Category</div>
                    <div style="font-size:12px;">${product.ai_suggested_category}</div>
                  </div>
                ` : ''}
                ${product.ai_description ? `
                  <div style="margin-top:8px;">
                    <div class="info-label" style="font-size:10px;font-weight:600;color:var(--text-dim);text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px;">Description</div>
                    <p style="font-size:12px;line-height:1.6;margin:0;">${product.ai_description}</p>
                  </div>
                ` : ''}
                ${product.ai_keywords?.length ? `
                  <div style="margin-top:8px;">
                    <div class="info-label" style="font-size:10px;font-weight:600;color:var(--text-dim);text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px;">Keywords</div>
                    <div class="tag-group">${product.ai_keywords.map(k => `<span class="tag tag-purple">${k}</span>`).join('')}</div>
                  </div>
                ` : ''}
              </div>
            ` : ''}

            ${(product.google_api_calls > 0) ? `
              <div class="card detail-card" style="border:1px solid rgba(234,179,8,0.2);">
                <div class="section-title" style="color:#eab308;">💰 Google API Cost</div>
                <div style="margin-top:8px;display:flex;flex-direction:column;gap:6px;">
                  <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span class="text-dim" style="font-size:11px;">API Calls</span>
                    <span style="font-size:12px;font-weight:600;">${product.google_api_calls}</span>
                  </div>
                  <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span class="text-dim" style="font-size:11px;">Estimated Cost</span>
                    <span style="font-size:13px;font-weight:700;color:#eab308;">$${Number(product.google_api_cost_usd).toFixed(4)}</span>
                  </div>
                </div>
              </div>
            ` : ''}

            ${product.material_info ? `
              <div class="card detail-card">
                <div class="section-title">Material</div>
                <p class="text-dim" style="font-size:12px;">${product.material_info}</p>
              </div>
            ` : ''}

            ${product.keywords?.length ? `
              <div class="card detail-card">
                <div class="section-title">Keywords</div>
                <div class="tag-group">${product.keywords.map(k => `<span class="tag tag-slate">${k}</span>`).join('')}</div>
              </div>
            ` : ''}

            <div class="card detail-card">
              <div class="section-title">Image Stats</div>
              <div class="stats-grid">
                <div class="stat-cell">${orig.length}<span>Original</span></div>
                <div class="stat-cell stat-blue">${ai.length}<span>AI Total</span></div>
                <div class="stat-cell stat-green">${approvedAI.length}<span>Approved</span></div>
                <div class="stat-cell stat-amber">${pendingAI.length}<span>Pending</span></div>
              </div>
            </div>
          </aside>

          <!-- Right: prompt card + image gallery -->
          <div class="detail-main">

            <!-- Prompt card -->
            <div class="card detail-card" id="prompt-card" style="margin-bottom:20px;">
              <div class="section-title">${icon.edit(11)} AI Prompt</div>

              ${!editingPrompt ? `
                <div class="prompt-text" style="min-height:48px;">${product.current_prompt?.prompt_text || '<span class="text-dim">No prompt set yet.</span>'}</div>
                <div class="prompt-meta text-dim">
                  ${product.current_prompt?.is_override ? '<span class="tag tag-amber">Custom</span>' : ''}
                  ${product.current_prompt?.created_by ? `by ${product.current_prompt.created_by.full_name}` : ''}
                </div>

                ${generatedPrompts && generatedPrompts.length ? `
                  <div class="ai-prompts-panel">
                    <div class="ai-prompts-header">
                      ${icon.sparkles(12)} Gemini — select a prompt
                      ${aiAnalysis && aiAnalysis.product_category ? `<span class="tag tag-blue">${aiAnalysis.product_category}</span>` : ''}
                    </div>
                    ${aiAnalysis && aiAnalysis.product_description ? `<p class="ai-prompts-desc">${aiAnalysis.product_description}</p>` : ''}
                    <div class="ai-prompt-cards">
                      ${generatedPrompts.map((p, i) => `
                        <div class="ai-prompt-card">
                          <div class="ai-prompt-card-header">
                            <span class="ai-prompt-setting">${p.setting_name}</span>
                          </div>
                          <div class="ai-prompt-card-tags tag-group">
                            ${(p.mood_tags || []).map(t => '<span class="tag tag-purple">' + t + '</span>').join('')}
                          </div>
                          <p class="ai-prompt-card-text">${p.prompt.length > 140 ? p.prompt.slice(0, 140) + '…' : p.prompt}</p>
                          <button class="btn btn-primary btn-sm btn-use-prompt" data-idx="${i}">
                            Use this prompt
                          </button>
                        </div>
                      `).join('')}
                    </div>
                  </div>
                ` : ''}

                <div class="prompt-cta-row">
                  <button id="btn-gen-ai-prompt" class="btn-cta btn-cta-purple" ${generatingAIPrompt ? 'disabled' : ''}>
                    ${generatingAIPrompt ? `${icon.loader(14)} Analyzing...` : `${icon.sparkles(14)} Generate Prompt`}
                  </button>
                  <button id="btn-regenerate" class="btn-cta btn-cta-green" ${product.status === 'AI_GENERATING' ? 'disabled' : ''}>
                    ${icon.sparkles(14)} Generate Image
                  </button>
                </div>
                <div class="prompt-secondary-row">
                  <button id="btn-edit-prompt" class="btn btn-secondary btn-sm">${icon.edit(12)} Edit Prompt</button>
                  <button id="btn-show-history" class="btn btn-secondary btn-sm">${icon.history(12)} History</button>
                </div>

                ${showHistory && promptHistory ? `
                  <div class="history-panel" style="margin-top:12px;">
                    <div class="section-title">Prompt History</div>
                    ${promptHistory.map(h => `
                      <div class="history-item">
                        <div class="history-text">${h.prompt_text}</div>
                        <div class="history-meta text-dim">${h.created_by?.full_name || ''} · ${new Date(h.created_at).toLocaleDateString()}</div>
                      </div>
                    `).join('')}
                  </div>
                ` : ''}
              ` : `
                <textarea id="prompt-textarea" class="input" rows="6" style="resize:vertical;">${promptDraft}</textarea>
                <div class="prompt-edit-actions">
                  <button id="btn-save-and-generate" class="btn-cta btn-cta-green">${icon.sparkles(14)} Save &amp; Generate Image</button>
                  <button id="btn-save-prompt" class="btn btn-primary">${icon.save(13)} Save Prompt</button>
                  <button id="btn-cancel-prompt" class="btn btn-secondary">Cancel</button>
                </div>
              `}
            </div>

            <div class="gallery-section">
              <div class="section-title">AI Generated Images</div>
              ${product.status === 'AI_FAILED' ? `
                <div style="padding:14px 16px;background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);border-radius:8px;margin-bottom:12px;">
                  <div style="font-size:13px;font-weight:600;color:#f87171;margin-bottom:4px;">⚠ Image generation failed</div>
                  <div style="font-size:11px;color:#f87171;font-family:monospace;word-break:break-word;">${product.generation_error || 'Unknown error'}</div>
                </div>
              ` : ''}
              ${ai.length === 0
                ? '<p class="text-dim" style="font-size:13px;">No AI images yet. Use "Generate Image" above.</p>'
                : '<div class="img-grid sortable-grid" id="ai-gallery">' + ai.map((img, i) => imageCard(img, i, 'AI')).join('') + '</div>'
              }
            </div>
            ${orig.length > 0 ? '<div class="gallery-section"><div class="section-title">Original Images</div><div class="img-grid" id="orig-gallery">' + orig.map((img, i) => imageCard(img, i, 'ORIGINAL')).join('') + '</div></div>' : ''}

          </div>
        </div>
      </div>

      <!-- Lightbox -->
      <div id="lightbox" class="lightbox" style="display:none;" role="dialog" aria-modal="true">
        <button class="lightbox-close" id="lb-close" title="Close (Esc)">${icon.xCircle(20)}</button>
        <button class="lightbox-nav lightbox-prev" id="lb-prev" title="Previous">${icon.chevLeft(26)}</button>
        <div class="lightbox-img-wrap">
          <img id="lb-img" src="" alt="">
        </div>
        <button class="lightbox-nav lightbox-next" id="lb-next" title="Next">${icon.chevRight(26)}</button>
        <div class="lightbox-caption" id="lb-caption"></div>
        <div class="lightbox-zoom-hint">Scroll to zoom &nbsp;·&nbsp; Drag to pan</div>
      </div>
    `

    // Back button
    container.querySelector('#btn-back')?.addEventListener('click', () => navigate('/'))
    container.querySelectorAll('[data-sibling]').forEach(el =>
      el.addEventListener('click', () => navigate(`/products/${el.dataset.sibling}`))
    )

    // Approve all
    container.querySelector('#btn-approve-all')?.addEventListener('click', async () => {
      const ids = pendingAI.map(i => i.key)
      try {
        const res = await approvalsApi.approve(sku, ids)
        toast.success(`${res.approved?.length || ids.length} image(s) approved`)
        product = await productsApi.get(sku)
        renderPage()
      } catch (err) { toast.error(err.message || 'Approval failed') }
    })

    // Per-image action buttons
    container.querySelectorAll('.img-action-approve').forEach(b => b.addEventListener('click', async (e) => {
      e.stopPropagation()
      try {
        await approvalsApi.approve(sku, [b.dataset.key])
        toast.success('Image approved')
        product = await productsApi.get(sku)
        renderPage()
      } catch (err) { toast.error(err.message || 'Approval failed') }
    }))

    container.querySelectorAll('.img-action-retry').forEach(b => b.addEventListener('click', async (e) => {
      e.stopPropagation()
      try {
        showGenerationModal()
        updateGenerationModal('image')
        await promptsApi.regenerate(sku)
        await loadProduct()
      } catch (err) {
        updateGenerationModal('error')
        showGenerationError(err.message || 'Retry failed')
      }
    }))

    container.querySelectorAll('.img-action-reject').forEach(b => b.addEventListener('click', async (e) => {
      e.stopPropagation()
      if (!confirm('Remove this AI image? This cannot be undone.')) return
      try {
        await approvalsApi.reject(sku, b.dataset.key)
        toast.success('Image removed')
        product = await productsApi.get(sku)
        renderPage()
      } catch (err) { toast.error(err.message || 'Remove failed') }
    }))

    container.querySelectorAll('.img-action-recall').forEach(b => b.addEventListener('click', async (e) => {
      e.stopPropagation()
      const reason = prompt('Recall reason (required):')
      if (!reason || reason.trim().length < 5) return
      try {
        await approvalsApi.recall(sku, b.dataset.key, reason.trim())
        toast.success('Image recalled')
        product = await productsApi.get(sku)
        renderPage()
      } catch (err) { toast.error(err.message || 'Recall failed') }
    }))

    // ── Lightbox ──────────────────────────────────────────────────────────────
    const lbEl      = container.querySelector('#lightbox')
    const lbImg     = container.querySelector('#lb-img')
    const lbCaption = container.querySelector('#lb-caption')
    let lbGallery = []
    let lbIndex   = 0

    let lbScale = 1, lbPanX = 0, lbPanY = 0
    function lbResetZoom() {
      lbScale = 1; lbPanX = 0; lbPanY = 0
      lbImg.style.transform = ''
      lbImg.style.cursor = 'zoom-in'
    }
    function lbApplyZoom() {
      lbImg.style.transform = `translate(${lbPanX}px, ${lbPanY}px) scale(${lbScale})`
      lbImg.style.cursor = lbScale > 1 ? 'grab' : 'zoom-in'
    }

    function lbClose() {
      lbEl.style.display = 'none'
      document.body.style.overflow = ''
      lbResetZoom()
    }
    function lbShow() {
      const item = lbGallery[lbIndex]
      if (!item) return
      lbImg.src = item.url
      lbResetZoom()
      lbCaption.textContent = `${item.label}  ·  ${lbIndex + 1} / ${lbGallery.length}`
      container.querySelector('#lb-prev').style.visibility = lbIndex > 0 ? 'visible' : 'hidden'
      container.querySelector('#lb-next').style.visibility = lbIndex < lbGallery.length - 1 ? 'visible' : 'hidden'
    }
    function lbOpen(gallery, idx) {
      lbGallery = gallery; lbIndex = idx
      lbShow()
      lbEl.style.display = 'flex'
      document.body.style.overflow = 'hidden'
    }

    lbEl?.addEventListener('wheel', e => {
      e.preventDefault()
      const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15
      lbScale = Math.min(Math.max(lbScale * factor, 1), 8)
      if (lbScale === 1) { lbPanX = 0; lbPanY = 0 }
      lbApplyZoom()
    }, { passive: false })

    let lbDragging = false, lbDragX = 0, lbDragY = 0, lbPanStartX = 0, lbPanStartY = 0
    lbImg?.addEventListener('mousedown', e => {
      if (lbScale <= 1) return
      lbDragging = true
      lbDragX = e.clientX; lbDragY = e.clientY
      lbPanStartX = lbPanX; lbPanStartY = lbPanY
      lbImg.style.cursor = 'grabbing'
      e.preventDefault()
    })
    document.addEventListener('mousemove', e => {
      if (!lbDragging) return
      lbPanX = lbPanStartX + (e.clientX - lbDragX)
      lbPanY = lbPanStartY + (e.clientY - lbDragY)
      lbApplyZoom()
    })
    document.addEventListener('mouseup', () => {
      if (lbDragging) { lbDragging = false; lbImg.style.cursor = lbScale > 1 ? 'grab' : 'zoom-in' }
    })

    container._lbClose = lbClose
    if (container._lbEsc) document.removeEventListener('keydown', container._lbEsc)
    container._lbEsc = e => { if (e.key === 'Escape') container._lbClose?.() }
    document.addEventListener('keydown', container._lbEsc)

    container.querySelectorAll('.img-open').forEach(el => {
      if (!el.dataset.url) return
      el.addEventListener('click', () => {
        const type     = el.dataset.type || 'ORIGINAL'
        const allThumbs = [...container.querySelectorAll(`.img-open[data-type="${type}"]`)].filter(t => t.dataset.url)
        const typeName  = type.charAt(0) + type.slice(1).toLowerCase()
        const gallery   = allThumbs.map((t, i) => ({ url: t.dataset.url, label: `${typeName} #${i + 1}` }))
        lbOpen(gallery, allThumbs.indexOf(el))
      })
    })

    container.querySelector('#lb-close')?.addEventListener('click', lbClose)
    container.querySelector('#lb-prev')?.addEventListener('click', () => { if (lbIndex > 0) { lbIndex--; lbShow() } })
    container.querySelector('#lb-next')?.addEventListener('click', () => { if (lbIndex < lbGallery.length - 1) { lbIndex++; lbShow() } })
    lbEl?.addEventListener('click', e => { if (e.target === lbEl) lbClose() })

    // Prompt editing
    container.querySelector('#btn-edit-prompt')?.addEventListener('click', () => {
      editingPrompt = true
      promptDraft = product.current_prompt?.prompt_text || ''
      renderPage()
    })
    container.querySelector('#btn-cancel-prompt')?.addEventListener('click', () => {
      editingPrompt = false; renderPage()
    })
    container.querySelector('#prompt-textarea')?.addEventListener('input', e => { promptDraft = e.target.value })
    container.querySelector('#btn-gen-ai-prompt')?.addEventListener('click', async () => {
      generatingAIPrompt = true
      aiAnalysis = null
      generatedPrompts = null
      renderPage()
      try {
        const res = await promptsApi.generateAI(sku)
        aiAnalysis = res.analysis
        generatedPrompts = res.prompts || []
        generatingAIPrompt = false
        product = await productsApi.get(sku)
        renderPage()
        toast.success('3 prompts generated — description, keywords & category updated')
      } catch (err) {
        generatingAIPrompt = false
        renderPage()
        toast.error(err.message || 'Gemini unavailable — check GOOGLE_SERVICE_ACCOUNT_FILE in .env')
      }
    })

    container.querySelectorAll('.btn-use-prompt').forEach(b => b.addEventListener('click', () => {
      const idx = parseInt(b.dataset.idx, 10)
      const p = generatedPrompts?.[idx]
      if (!p) return
      promptDraft = p.prompt
      editingPrompt = true
      generatedPrompts = null
      renderPage()
    }))

    container.querySelector('#btn-save-prompt')?.addEventListener('click', async () => {
      try {
        await promptsApi.update(sku, promptDraft)
        toast.success('Prompt saved')
        editingPrompt = false
        product = await productsApi.get(sku)
        renderPage()
      } catch (err) { toast.error(err.message || 'Save failed') }
    })

    container.querySelector('#btn-save-and-generate')?.addEventListener('click', async () => {
      try {
        showGenerationModal()
        updateGenerationModal('prompt')
        await promptsApi.update(sku, promptDraft)
        editingPrompt = false
        updateGenerationModal('image')
        await promptsApi.regenerate(sku)
        await loadProduct()
      } catch (err) {
        updateGenerationModal('error')
        showGenerationError(err.message || 'Failed')
      }
    })

    container.querySelector('#btn-regenerate')?.addEventListener('click', async () => {
      try {
        showGenerationModal()
        updateGenerationModal('image')
        await promptsApi.regenerate(sku)
        await loadProduct()
      } catch (err) {
        updateGenerationModal('error')
        showGenerationError(err.message || 'Failed')
      }
    })

    container.querySelector('#btn-show-history')?.addEventListener('click', async () => {
      if (!promptHistory) {
        try { promptHistory = await promptsApi.history(sku) } catch {}
      }
      showHistory = !showHistory
      renderPage()
    })

    // Sortable AI gallery
    const aiGallery = container.querySelector('#ai-gallery')
    if (aiGallery && window.Sortable) {
      sortable = window.Sortable.create(aiGallery, {
        animation: 150,
        handle: '.img-drag-handle',
        ghostClass: 'sortable-ghost',
        async onEnd() {
          const order = [...aiGallery.querySelectorAll('[data-key]')].map(el => el.dataset.key)
          try { await approvalsApi.reorder(sku, order) }
          catch { toast.error('Failed to save image order') }
        }
      })
    }
  }

  container.innerHTML = `<div class="loading">${icon.loader(24)}<span>Loading...</span></div>`
  await loadProduct()

  return () => {
    clearInterval(pollTimer); pollTimer = null
    if (container._lbEsc) document.removeEventListener('keydown', container._lbEsc)
    document.body.style.overflow = ''
  }
}
