import { promptsApi } from '../api.js'
import { toast } from '../toast.js'
import { icon } from '../icons.js'

export async function render(container) {
  let state = {
    mode: null,          // 'photoshoot' | 'creative'
    prompt: '',
    file: null,
    fileDataUrl: null,
    generating: false,
    result: null,        // { image_data, mime_type }
  }

  function modeDefaults(m) {
    return m === 'photoshoot'
      ? 'A professional fashion model wearing this exact garment, photographed in a minimalist Nordic studio setting with soft natural light, editorial quality, full-body shot'
      : ''
  }

  function renderPage() {
    const hasSource = !!state.fileDataUrl
    const hasResult = !!state.result
    const resultSrc = hasResult ? `data:${state.result.mime_type};base64,${state.result.image_data}` : ''

    container.innerHTML = `
      <div class="ps-page">

        <!-- Hero -->
        <div class="ps-hero">
          <div class="ps-hero-glow"></div>
          <div class="ps-hero-inner">
            <div class="ps-hero-icon">${icon.wand(28)}</div>
            <h1 class="ps-hero-title">AI Photoshoot</h1>
            <p class="ps-hero-sub">Generate professional model &amp; lifestyle images with Gemini AI</p>
          </div>
        </div>

        <!-- Mode cards -->
        <div class="ps-modes">

          <div class="ps-mode-card ${state.mode === 'photoshoot' ? 'ps-mode-active' : ''}" data-mode="photoshoot">
            <div class="ps-mode-badge">Recommended</div>
            <div class="ps-mode-head">
              <div class="ps-mode-icon">${icon.image(22)}</div>
              <div>
                <div class="ps-mode-title">Model Photoshoot</div>
                <div class="ps-mode-desc">Upload your product image and dress it on a professional model in a premium retail setting</div>
              </div>
            </div>
            <div class="ps-mode-preview ps-preview-mosaic">
              <div class="ps-mosaic-grid">
                <div class="ps-mosaic-cell" style="background:linear-gradient(135deg,#2d2040,#4a3060);"></div>
                <div class="ps-mosaic-cell" style="background:linear-gradient(135deg,#1a2a4a,#2a4070);"></div>
                <div class="ps-mosaic-cell" style="background:linear-gradient(135deg,#3a2a1a,#6a4a2a);"></div>
                <div class="ps-mosaic-cell" style="background:linear-gradient(135deg,#1a3a2a,#2a5a40);"></div>
              </div>
              <div class="ps-mosaic-overlay">
                <div class="ps-mosaic-cta">${icon.sparkles(14)} Upload &amp; Shoot</div>
              </div>
            </div>
          </div>

          <div class="ps-mode-card ${state.mode === 'creative' ? 'ps-mode-active' : ''}" data-mode="creative">
            <div class="ps-mode-head">
              <div class="ps-mode-icon">${icon.edit(22)}</div>
              <div>
                <div class="ps-mode-title">Creative Studio</div>
                <div class="ps-mode-desc">Generate or edit any image freely — write a prompt and let Gemini create the scene</div>
              </div>
            </div>
            <div class="ps-mode-preview ps-preview-creative">
              <div class="ps-creative-scene">
                <div class="ps-creative-bar" style="width:65%;background:rgba(99,102,241,0.6);"></div>
                <div class="ps-creative-bar" style="width:45%;background:rgba(167,139,250,0.5);"></div>
                <div class="ps-creative-bar" style="width:80%;background:rgba(99,102,241,0.4);"></div>
              </div>
              <div class="ps-mosaic-overlay">
                <div class="ps-mosaic-cta">${icon.sparkles(14)} Open Studio</div>
              </div>
            </div>
          </div>

        </div>

        <!-- Workspace (visible after mode selected) -->
        ${state.mode ? `
          <div class="ps-workspace" id="ps-workspace">
            <div class="ps-workspace-header">
              <div class="ps-workspace-title">
                ${state.mode === 'photoshoot' ? icon.image(16) + ' Model Photoshoot' : icon.edit(16) + ' Creative Studio'}
              </div>
              <button class="ps-workspace-close" id="btn-close-mode">${icon.xCircle(15)} Close</button>
            </div>

            <div class="ps-workspace-body">

              <!-- Upload panel -->
              <div class="ps-upload-panel">
                <div class="ps-panel-label">
                  ${state.mode === 'photoshoot' ? 'Product Image' : 'Source Image'}
                  ${state.mode === 'photoshoot'
                    ? '<span class="ps-required">Required</span>'
                    : '<span class="ps-optional">Optional</span>'}
                </div>

                ${hasSource ? `
                  <div class="ps-thumb-zone">
                    <div class="ps-thumb" data-expand="source">
                      <img src="${state.fileDataUrl}" alt="" class="ps-thumb-img">
                      <div class="ps-thumb-hover">
                        <span>${icon.expand(16)}</span>
                      </div>
                    </div>
                    <div class="ps-thumb-meta">
                      <div class="ps-thumb-name">${state.file ? state.file.name : 'image'}</div>
                      <div class="ps-thumb-size">${state.file ? (state.file.size / 1024).toFixed(0) + ' KB' : ''}</div>
                      <button class="ps-thumb-remove" id="btn-remove-img">${icon.xCircle(13)} Remove</button>
                      <div class="ps-reupload" id="ps-upload-area">${icon.image(12)} Change
                        <input type="file" id="ps-file-input" accept="image/*" style="display:none;">
                      </div>
                    </div>
                  </div>
                ` : `
                  <div class="ps-dropzone ${state.mode === 'photoshoot' ? 'ps-dropzone-required' : ''}" id="ps-upload-area">
                    <div class="ps-dropzone-body">
                      <div class="ps-dropzone-icon-wrap">${icon.image(30)}</div>
                      <div class="ps-dropzone-title">
                        ${state.mode === 'photoshoot' ? 'Upload your product image' : 'Drop an image to edit'}
                      </div>
                      <div class="ps-dropzone-hint">Drag &amp; drop or <span class="ps-link">browse files</span></div>
                      <div class="ps-dropzone-formats">PNG &nbsp;·&nbsp; JPG &nbsp;·&nbsp; WEBP</div>
                    </div>
                    <input type="file" id="ps-file-input" accept="image/*" style="display:none;">
                  </div>
                `}
              </div>

              <!-- Prompt panel -->
              <div class="ps-prompt-panel">
                <div class="ps-panel-label">Prompt</div>
                <textarea id="ps-prompt" class="ps-textarea"
                  placeholder="${state.mode === 'photoshoot'
                    ? 'Describe the scene — Nordic studio, outdoor setting, model pose, lighting style…'
                    : 'Describe what you want to create or how you want to edit the image…'
                  }">${state.prompt}</textarea>
                <button id="btn-generate" class="ps-generate-btn" ${state.generating ? 'disabled' : ''}>
                  ${state.generating
                    ? `<span class="ps-btn-spinner">${icon.loader(16)}</span> Generating…`
                    : `${icon.sparkles(16)} ${state.mode === 'photoshoot' ? 'Shoot' : 'Generate'}`}
                </button>
                ${state.generating ? '<div class="ps-gen-hint">Gemini is creating your image — 15–30 seconds</div>' : ''}
              </div>

            </div>
          </div>
        ` : ''}

        <!-- Result -->
        ${hasResult ? `
          <div class="ps-result" id="ps-result">
            <div class="ps-result-bar">
              <div class="ps-result-title">${icon.sparkles(15)} Result
                <span class="tag tag-green" style="font-size:11px;margin-left:8px;">Ready</span>
              </div>
              <div class="ps-result-actions">
                <button id="btn-new-gen" class="btn btn-secondary btn-sm">${icon.plus(12)} New</button>
                <a class="btn btn-primary btn-sm" download="generated.png" href="${resultSrc}">
                  ${icon.save(12)} Download
                </a>
              </div>
            </div>

            ${hasSource ? `
              <!-- Before / After -->
              <div class="ps-ba">
                <div class="ps-ba-half">
                  <div class="ps-ba-label">
                    <span class="ps-ba-dot ps-dot-before"></span>
                    Before
                  </div>
                  <div class="ps-ba-img-wrap" data-expand="source">
                    <img src="${state.fileDataUrl}" alt="" class="ps-ba-img">
                    <div class="ps-ba-expand">${icon.expand(14)}</div>
                  </div>
                </div>
                <div class="ps-ba-arrow">
                  <div class="ps-ba-line"></div>
                  <div class="ps-ba-chevron">${icon.chevRight(18)}</div>
                  <div class="ps-ba-line"></div>
                </div>
                <div class="ps-ba-half">
                  <div class="ps-ba-label">
                    <span class="ps-ba-dot ps-dot-after"></span>
                    After — AI Generated
                  </div>
                  <div class="ps-ba-img-wrap" data-expand="result">
                    <img src="${resultSrc}" alt="" class="ps-ba-img">
                    <div class="ps-ba-expand">${icon.expand(14)}</div>
                  </div>
                </div>
              </div>
            ` : `
              <div class="ps-single-result">
                <div class="ps-single-wrap" data-expand="result">
                  <img src="${resultSrc}" alt="" class="ps-single-img">
                  <div class="ps-ba-expand">${icon.expand(16)}</div>
                </div>
                <p class="ps-single-hint">Click to expand</p>
              </div>
            `}
          </div>

          <!-- Lightbox -->
          <div id="ps-lightbox" class="ps-lightbox" style="display:none;">
            <div class="ps-lb-bg" id="ps-lb-bg"></div>
            <button class="ps-lb-close" id="ps-lb-close">${icon.xCircle(24)}</button>
            <div class="ps-lb-wrap"><img id="ps-lb-img" src="" alt=""></div>
            <div class="ps-lb-cap" id="ps-lb-cap"></div>
          </div>
        ` : ''}

      </div>
    `

    bindEvents(resultSrc)
  }

  function bindEvents(resultSrc) {
    // Mode selection
    container.querySelectorAll('.ps-mode-card').forEach(card => {
      card.addEventListener('click', () => {
        const m = card.dataset.mode
        if (state.mode === m) return
        state.mode = m
        state.prompt = modeDefaults(m)
        state.result = null
        renderPage()
        setTimeout(() => {
          container.querySelector('#ps-workspace')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }, 80)
      })
    })

    container.querySelector('#btn-close-mode')?.addEventListener('click', () => {
      state.mode = null; state.result = null; renderPage()
    })

    // Upload
    const uploadArea = container.querySelector('#ps-upload-area')
    const fileInput  = container.querySelector('#ps-file-input')
    uploadArea?.addEventListener('click', e => {
      if (e.target.closest('#btn-remove-img') || e.target.closest('.ps-thumb-remove')) return
      fileInput?.click()
    })
    const dz = container.querySelector('.ps-dropzone')
    if (dz) {
      dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('dz-over') })
      dz.addEventListener('dragleave', () => dz.classList.remove('dz-over'))
      dz.addEventListener('drop', e => {
        e.preventDefault(); dz.classList.remove('dz-over')
        const f = e.dataTransfer.files[0]; if (f) loadFile(f)
      })
    }
    fileInput?.addEventListener('change', () => { if (fileInput.files[0]) loadFile(fileInput.files[0]) })
    container.querySelector('#btn-remove-img')?.addEventListener('click', e => {
      e.stopPropagation()
      state.file = null; state.fileDataUrl = null; state.result = null; renderPage()
    })

    // Prompt
    container.querySelector('#ps-prompt')?.addEventListener('input', e => { state.prompt = e.target.value })

    // Generate
    container.querySelector('#btn-generate')?.addEventListener('click', generate)
    container.querySelector('#btn-new-gen')?.addEventListener('click', () => { state.result = null; renderPage() })

    // Lightbox
    const lb    = container.querySelector('#ps-lightbox')
    const lbImg = container.querySelector('#ps-lb-img')
    const lbCap = container.querySelector('#ps-lb-cap')
    const closeLb = () => { if (lb) lb.style.display = 'none'; document.body.style.overflow = '' }
    container.querySelectorAll('[data-expand]').forEach(el => {
      el.addEventListener('click', () => {
        if (!lb || !lbImg) return
        lbImg.src = el.dataset.expand === 'source' ? state.fileDataUrl : resultSrc
        if (lbCap) lbCap.textContent = el.dataset.expand === 'source' ? (state.file?.name || 'Source') : 'AI Generated'
        lb.style.display = 'flex'; document.body.style.overflow = 'hidden'
      })
    })
    container.querySelector('#ps-lb-close')?.addEventListener('click', closeLb)
    container.querySelector('#ps-lb-bg')?.addEventListener('click', closeLb)
    if (lb) {
      if (container._psEsc) document.removeEventListener('keydown', container._psEsc)
      container._psEsc = e => { if (e.key === 'Escape') closeLb() }
      document.addEventListener('keydown', container._psEsc)
    }
  }

  async function generate() {
    const prompt = container.querySelector('#ps-prompt')?.value.trim()
    if (!prompt) { toast.error('Please enter a prompt'); return }
    if (state.mode === 'photoshoot' && !state.file) { toast.error('Please upload a product image'); return }
    state.prompt = prompt
    state.generating = true; state.result = null; renderPage()
    try {
      const fd = new FormData()
      fd.append('prompt', prompt)
      if (state.file) fd.append('source_image', state.file)
      const res = await promptsApi.standaloneGenerate(fd)
      state.result = res; state.generating = false; renderPage()
      toast.success('Image generated!')
      setTimeout(() => container.querySelector('#ps-result')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80)
    } catch (err) {
      state.generating = false; renderPage()
      toast.error(err.message || 'Generation failed — check Gemini configuration')
    }
  }

  function loadFile(file) {
    state.file = file
    const reader = new FileReader()
    reader.onload = e => { state.fileDataUrl = e.target.result; state.result = null; renderPage() }
    reader.readAsDataURL(file)
  }

  renderPage()
  return () => {
    if (container._psEsc) document.removeEventListener('keydown', container._psEsc)
    document.body.style.overflow = ''
  }
}
