import { analyticsApi } from '../api.js'
import { toast } from '../toast.js'
import { icon } from '../icons.js'

let charts = []

function destroyCharts() {
  charts.forEach(c => c.destroy())
  charts = []
}

function getChartTheme() {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark'
  return {
    textColor:  isDark ? '#a1a1aa' : '#71717a',
    gridColor:  isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.06)',
    tickColor:  isDark ? '#71717a' : '#a1a1aa',
  }
}

export async function render(container) {
  let days = 30

  async function load() {
    destroyCharts()
    container.innerHTML = `<div class="loading">${icon.loader(24)}<span>Loading analytics...</span></div>`
    let data
    try { data = await analyticsApi.summary(days) }
    catch { toast.error('Failed to load analytics'); return }

    const { total_products_ingested: ingested, total_ai_generated: generated,
            total_manual_photoshoot: manualShoot,
            total_approved: approved, total_recalled: recalled,
            total_ai_rejected: rejected,
            approval_rate, daily_trend, by_brand,
            total_google_api_calls: googleCalls = 0,
            total_google_cost_usd: googleCost = 0 } = data

    container.innerHTML = `
      <div class="page-content">
        <div class="page-header">
          <h1 class="page-title">Analytics</h1>
          <div class="days-selector">
            ${[7, 30, 90].map(d => `
              <button class="btn btn-secondary days-btn ${days === d ? 'active' : ''}" data-days="${d}">${d} days</button>
            `).join('')}
          </div>
        </div>

        <div class="stat-cards">
          <div class="stat-card">
            <div class="stat-value">${ingested}</div>
            <div class="stat-label">Products Ingested</div>
          </div>
          <div class="stat-card stat-blue">
            <div class="stat-value">${generated}</div>
            <div class="stat-label">AI Generated</div>
          </div>
          <div class="stat-card stat-blue">
            <div class="stat-value">${manualShoot}</div>
            <div class="stat-label">Manual Photoshoot</div>
          </div>
          <div class="stat-card stat-green">
            <div class="stat-value">${approved}</div>
            <div class="stat-label">Approved</div>
          </div>
          <div class="stat-card stat-red">
            <div class="stat-value">${recalled}</div>
            <div class="stat-label">Recalled</div>
          </div>
          <div class="stat-card stat-red">
            <div class="stat-value">${rejected}</div>
            <div class="stat-label">AI Images Rejected</div>
          </div>
        </div>

        <div class="stat-cards" style="margin-top:0;">
          <div class="stat-card" style="border:1px solid rgba(234,179,8,0.3);background:rgba(234,179,8,0.06);">
            <div class="stat-value" style="color:#eab308;">${googleCalls}</div>
            <div class="stat-label">Google API Calls</div>
          </div>
          <div class="stat-card" style="border:1px solid rgba(234,179,8,0.3);background:rgba(234,179,8,0.06);">
            <div class="stat-value" style="color:#eab308;">$${Number(googleCost).toFixed(4)}</div>
            <div class="stat-label">Estimated Google Cost (USD)</div>
          </div>
        </div>

        <div class="card" style="padding:20px;margin-bottom:16px;">
          <div class="section-title">Approval Rate</div>
          <div class="approval-rate-row">
            <div class="approval-rate-pct">${approval_rate}%</div>
            <div class="approval-rate-bar-wrap">
              <div class="approval-rate-bar" style="width:${approval_rate}%"></div>
            </div>
          </div>
        </div>

        <div class="chart-grid">
          <div class="card chart-card">
            <div class="section-title">Daily Activity (last ${days} days)</div>
            <div style="position:relative;height:240px;">
              <canvas id="chart-daily"></canvas>
            </div>
          </div>
          <div class="card chart-card">
            <div class="section-title">By Brand</div>
            <div style="position:relative;height:240px;">
              <canvas id="chart-brand"></canvas>
            </div>
          </div>
        </div>
      </div>
    `

    container.querySelectorAll('.days-btn').forEach(b => b.addEventListener('click', () => {
      days = parseInt(b.dataset.days)
      load()
    }))

    if (window.Chart) {
      const { textColor, gridColor, tickColor } = getChartTheme()

      const chartOpts = {
        plugins: { legend: { labels: { color: textColor, font: { size: 12 } } } },
        scales: {
          x: { ticks: { color: tickColor }, grid: { color: gridColor } },
          y: { ticks: { color: tickColor }, grid: { color: gridColor } },
        },
      }

      const dailyCtx = document.getElementById('chart-daily')
      if (dailyCtx && daily_trend?.length) {
        charts.push(new window.Chart(dailyCtx, {
          type: 'line',
          data: {
            labels: daily_trend.map(d => d.date),
            datasets: [
              { label: 'Generated', data: daily_trend.map(d => d.generated), borderColor: '#6366f1', backgroundColor: 'rgba(99,102,241,0.1)', tension: 0.4, fill: true },
              { label: 'Approved',  data: daily_trend.map(d => d.approved),  borderColor: '#22c55e', backgroundColor: 'rgba(34,197,94,0.1)',  tension: 0.4, fill: true },
              { label: 'Recalled',  data: daily_trend.map(d => d.recalled),  borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.1)',  tension: 0.4, fill: true },
            ],
          },
          options: { responsive: true, maintainAspectRatio: false, ...chartOpts },
        }))
      }

      const brandCtx = document.getElementById('chart-brand')
      if (brandCtx && by_brand?.length) {
        charts.push(new window.Chart(brandCtx, {
          type: 'bar',
          data: {
            labels: by_brand.map(b => b.brand_name),
            datasets: [
              { label: 'Total',    data: by_brand.map(b => b.total_products), backgroundColor: 'rgba(99,102,241,0.5)' },
              { label: 'Approved', data: by_brand.map(b => b.approved),       backgroundColor: 'rgba(34,197,94,0.5)' },
            ],
          },
          options: { responsive: true, maintainAspectRatio: false, ...chartOpts },
        }))
      }
    }
  }

  await load()
  return () => destroyCharts()
}
