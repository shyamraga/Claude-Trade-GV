/**
 * Claude Trading Dashboard Application Logic
 * Implements high-performance Canvas financial charts, REST polling,
 * circuit breaker cooldown tracking, post-mortem learning inspection, and order dispatch.
 */

// Global Application State
const state = {
  activeSymbol: 'SPY',
  activeTimeframe: '15m',
  chartType: 'candle', // 'candle' or 'line'
  bars: [],
  account: null,
  positions: [],
  circuitBreaker: null,
  trades: [],
  postMortems: [],
  cooldownTimerInterval: null,
  pollInterval: null,
};

// Formatting Utilities
const formatCurrency = (val) => {
  const num = Number(val) || 0;
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num);
};

const formatPct = (val) => {
  const num = Number(val) || 0;
  const sign = num > 0 ? '+' : '';
  return `${sign}${(num * 100).toFixed(2)}%`;
};

// Toast Notifications
function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️';
  toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

/* ==========================================================================
   CANVAS FINANCIAL CHART RENDERER
   ========================================================================== */
class FinancialChartRenderer {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas ? this.canvas.getContext('2d') : null;
    this.tooltip = document.getElementById('chartTooltip');
    this.crosshair = { active: false, x: 0, y: 0 };
    this.setupListeners();
  }

  setupListeners() {
    if (!this.canvas) return;

    window.addEventListener('resize', () => this.render());

    this.canvas.addEventListener('mousemove', (e) => {
      const rect = this.canvas.getBoundingClientRect();
      this.crosshair.active = true;
      this.crosshair.x = e.clientX - rect.left;
      this.crosshair.y = e.clientY - rect.top;
      this.render();
    });

    this.canvas.addEventListener('mouseleave', () => {
      this.crosshair.active = false;
      if (this.tooltip) this.tooltip.classList.add('hidden');
      this.render();
    });
  }

  resizeCanvas() {
    const parent = this.canvas.parentElement;
    const dpr = window.devicePixelRatio || 1;
    const width = parent.clientWidth;
    const height = parent.clientHeight;

    this.canvas.width = width * dpr;
    this.canvas.height = height * dpr;
    this.ctx.scale(dpr, dpr);
    return { width, height };
  }

  render() {
    if (!this.ctx || !state.bars || state.bars.length === 0) return;

    const { width, height } = this.resizeCanvas();
    const ctx = this.ctx;
    const bars = state.bars;

    // Layout configuration
    const padding = { top: 20, right: 65, bottom: 25, left: 15 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;
    const volumeHeight = chartHeight * 0.18;
    const priceChartHeight = chartHeight - volumeHeight - 15;

    // Clear background
    ctx.fillStyle = '#03060C';
    ctx.fillRect(0, 0, width, height);

    // Compute price and volume bounds
    let minPrice = Infinity;
    let maxPrice = -Infinity;
    let maxVolume = 0;

    bars.forEach((b) => {
      if (b.low < minPrice) minPrice = b.low;
      if (b.high > maxPrice) maxPrice = b.high;
      if (b.volume > maxVolume) maxVolume = b.volume;
    });

    const priceBuffer = (maxPrice - minPrice) * 0.08 || 1;
    minPrice -= priceBuffer;
    maxPrice += priceBuffer;
    const priceRange = maxPrice - minPrice;

    // Helper coordinates
    const getX = (index) => padding.left + (index + 0.5) * (chartWidth / bars.length);
    const getY = (price) => padding.top + (1 - (price - minPrice) / priceRange) * priceChartHeight;
    const candleWidth = Math.max(3, (chartWidth / bars.length) * 0.65);

    // Draw Price Grid Lines
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    ctx.lineWidth = 1;
    ctx.fillStyle = '#64748B';
    ctx.font = '10px "JetBrains Mono", monospace';
    ctx.textAlign = 'left';

    const gridSteps = 5;
    for (let i = 0; i <= gridSteps; i++) {
      const p = minPrice + (priceRange / gridSteps) * i;
      const y = getY(p);

      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(width - padding.right, y);
      ctx.stroke();

      ctx.fillText(p.toFixed(2), width - padding.right + 8, y + 3);
    }

    // Draw Volume Bars
    const volBaseY = height - padding.bottom;
    bars.forEach((b, idx) => {
      const x = getX(idx);
      const isUp = b.close >= b.open;
      const vHeight = maxVolume > 0 ? (b.volume / maxVolume) * volumeHeight : 0;
      const y = volBaseY - vHeight;

      ctx.fillStyle = isUp ? 'rgba(38, 166, 154, 0.3)' : 'rgba(239, 83, 80, 0.3)';
      ctx.fillRect(x - candleWidth / 2, y, candleWidth, vHeight);
    });

    // Draw Price Series (Candles or Line)
    if (state.chartType === 'candle') {
      bars.forEach((b, idx) => {
        const x = getX(idx);
        const openY = getY(b.open);
        const closeY = getY(b.close);
        const highY = getY(b.high);
        const lowY = getY(b.low);
        const isUp = b.close >= b.open;
        const color = isUp ? '#26A69A' : '#EF5350';

        // Draw Wick
        ctx.strokeStyle = color;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, highY);
        ctx.lineTo(x, lowY);
        ctx.stroke();

        // Draw Candle Body
        ctx.fillStyle = color;
        const bodyTop = Math.min(openY, closeY);
        const bodyHeight = Math.max(2, Math.abs(closeY - openY));
        ctx.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight);
      });
    } else {
      // Area / Line Chart
      ctx.beginPath();
      ctx.moveTo(getX(0), getY(bars[0].close));
      for (let i = 1; i < bars.length; i++) {
        ctx.lineTo(getX(i), getY(bars[i].close));
      }

      ctx.strokeStyle = '#38BDF8';
      ctx.lineWidth = 2;
      ctx.stroke();

      // Gradient Fill
      ctx.lineTo(getX(bars.length - 1), priceChartHeight + padding.top);
      ctx.lineTo(getX(0), priceChartHeight + padding.top);
      ctx.closePath();
      const grad = ctx.createLinearGradient(0, padding.top, 0, priceChartHeight + padding.top);
      grad.addColorStop(0, 'rgba(56, 189, 248, 0.25)');
      grad.addColorStop(1, 'rgba(56, 189, 248, 0.0)');
      ctx.fillStyle = grad;
      ctx.fill();
    }

    // Interactive Crosshair and Hover Tooltip
    if (this.crosshair.active && this.crosshair.x >= padding.left && this.crosshair.x <= width - padding.right) {
      const candleSlotWidth = chartWidth / bars.length;
      const barIdx = Math.floor((this.crosshair.x - padding.left) / candleSlotWidth);

      if (barIdx >= 0 && barIdx < bars.length) {
        const hoveredBar = bars[barIdx];
        const snappedX = getX(barIdx);

        // Vertical and horizontal dashed lines
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.35)';
        ctx.setLineDash([4, 4]);
        ctx.lineWidth = 1;

        ctx.beginPath();
        ctx.moveTo(snappedX, padding.top);
        ctx.lineTo(snappedX, height - padding.bottom);
        ctx.stroke();

        ctx.beginPath();
        ctx.moveTo(padding.left, this.crosshair.y);
        ctx.lineTo(width - padding.right, this.crosshair.y);
        ctx.stroke();
        ctx.setLineDash([]);

        // Show HTML Tooltip
        if (this.tooltip) {
          const isUp = hoveredBar.close >= hoveredBar.open;
          const diff = hoveredBar.close - hoveredBar.open;
          const diffPct = (diff / hoveredBar.open) * 100;
          this.tooltip.innerHTML = `
            <div style="font-weight:700; color:#38BDF8; margin-bottom:4px;">${hoveredBar.timestamp.replace('T', ' ')}</div>
            <div>O: <strong>$${hoveredBar.open.toFixed(2)}</strong></div>
            <div>H: <strong>$${hoveredBar.high.toFixed(2)}</strong></div>
            <div>L: <strong>$${hoveredBar.low.toFixed(2)}</strong></div>
            <div>C: <strong style="color:${isUp ? '#26A69A' : '#EF5350'}">$${hoveredBar.close.toFixed(2)} (${diffPct.toFixed(2)}%)</strong></div>
            <div>Vol: <strong>${Number(hoveredBar.volume).toLocaleString()}</strong></div>
          `;
          this.tooltip.style.left = `${Math.min(width - 160, snappedX + 15)}px`;
          this.tooltip.style.top = `${Math.min(height - 120, Math.max(10, this.crosshair.y - 40))}px`;
          this.tooltip.classList.remove('hidden');
        }
      }
    }
  }
}

// Global chart instance
let chartRenderer = null;

/* ==========================================================================
   API DATA FETCHING & SYNCHRONIZATION
   ========================================================================== */
async function fetchAccountData() {
  try {
    const res = await fetch('/api/account');
    if (!res.ok) return;
    const data = await res.json();
    state.account = data;

    // Update Header and Cards
    const valPortfolio = formatCurrency(data.portfolio_value);
    const valCash = formatCurrency(data.cash);
    const valBuyingPower = formatCurrency(data.buying_power);

    document.getElementById('hdrPortfolioVal').textContent = valPortfolio;
    document.getElementById('hdrCashVal').textContent = valCash;
    document.getElementById('cardEquity').textContent = valPortfolio;
    document.getElementById('cardBuyingPower').textContent = valBuyingPower;

    // Day Trades
    const dayTrades = data.day_trades_remaining ?? 3;
    document.getElementById('hdrDayTrades').textContent = `${dayTrades} / 3`;

    // Mode Sync
    const isLive = data.mode === 'LIVE';
    document.getElementById('engineModeText').textContent = isLive ? 'LIVE BROKER' : 'VIRTUAL MODE';
    document.getElementById('btnLiveMode').classList.toggle('active', isLive);
    document.getElementById('btnVirtualMode').classList.toggle('active', !isLive);

    const badge = document.getElementById('engineStatusBadge');
    if (isLive) {
      badge.style.borderColor = 'rgba(239, 83, 80, 0.4)';
      badge.style.color = '#EF5350';
    } else {
      badge.style.borderColor = 'rgba(56, 189, 248, 0.3)';
      badge.style.color = '#38BDF8';
    }
  } catch (err) {
    console.error('Failed to fetch account:', err);
  }
}

async function fetchPositionsData() {
  try {
    const res = await fetch('/api/positions');
    if (!res.ok) return;
    const data = await res.json();
    state.positions = data.positions || [];

    const tbody = document.getElementById('positionsTableBody');
    const countBadge = document.getElementById('openPositionCount');
    countBadge.textContent = `${state.positions.length} Open`;

    if (state.positions.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted py-6">No open positions. Ready to trade.</td></tr>`;
      return;
    }

    tbody.innerHTML = state.positions
      .map((p) => {
        const isProfit = (p.unrealized_pnl || 0) >= 0;
        const pnlClass = isProfit ? 'positive' : 'negative';
        const mktVal = (p.quantity || 0) * (p.current_price || p.entry_price || 0);

        return `
          <tr>
            <td style="font-weight:700;">${p.symbol}</td>
            <td><span class="trade-action-tag BUY">LONG</span></td>
            <td class="text-right">${p.quantity}</td>
            <td class="text-right">${formatCurrency(p.entry_price)}</td>
            <td class="text-right">${formatCurrency(p.current_price)}</td>
            <td class="text-right">${formatCurrency(mktVal)}</td>
            <td class="text-right pnl-text ${pnlClass}">
              ${formatCurrency(p.unrealized_pnl)} (${formatPct(p.unrealized_pnl_pct)})
            </td>
            <td class="text-center">
              <button class="btn-mini-exit" onclick="quickExitPosition('${p.symbol}', ${p.current_price || p.entry_price})">
                EXIT
              </button>
            </td>
          </tr>
        `;
      })
      .join('');
  } catch (err) {
    console.error('Failed to fetch positions:', err);
  }
}

async function fetchCircuitBreakerData() {
  try {
    const res = await fetch('/api/circuit-breaker');
    if (!res.ok) return;
    const cb = await res.json();
    state.circuitBreaker = cb;

    const circuitCard = document.getElementById('circuitCard');
    const circuitPill = document.getElementById('circuitPill');
    const btnOverride = document.getElementById('btnToggleOverride');
    const cooldownBanner = document.getElementById('cooldownBanner');
    const lossDots = document.querySelectorAll('#lossPills .loss-dot');
    const lossCountText = document.getElementById('lossCountText');
    const drawdownBar = document.getElementById('drawdownBar');
    const currentDrawdownText = document.getElementById('currentDrawdownText');

    // Consecutive Losses Dots
    const losses = cb.consecutive_losses || 0;
    lossCountText.textContent = `${losses} / ${cb.consecutive_loss_limit || 3}`;
    lossDots.forEach((dot, idx) => {
      dot.classList.toggle('filled', idx < losses);
    });

    // Drawdown Progress
    const ddPct = cb.current_drawdown_pct || 0;
    const maxDdPct = cb.max_daily_drawdown_pct || 0.03;
    const progressFill = Math.min(100, Math.max(0, (ddPct / maxDdPct) * 100));

    drawdownBar.style.width = `${progressFill}%`;
    drawdownBar.className = 'progress-bar-fill';
    if (progressFill >= 85) drawdownBar.classList.add('danger');
    else if (progressFill >= 50) drawdownBar.classList.add('warning');

    currentDrawdownText.textContent = `${(ddPct * 100).toFixed(2)}%`;

    // Manual Override State
    btnOverride.classList.toggle('active', !!cb.manual_override);

    // Cooldown status and Live Countdown
    if (cb.is_cooldown_active && !cb.manual_override) {
      circuitCard.classList.add('cooldown-active');
      circuitPill.className = 'status-pill cooldown';
      circuitPill.textContent = 'COOLDOWN ACTIVE';

      cooldownBanner.classList.remove('hidden');
      document.getElementById('cooldownReasonText').textContent = cb.cooldown_reason || 'Safety limit hit';
      startCooldownCountdown(cb.cooldown_until);
    } else if (cb.manual_override) {
      circuitCard.classList.remove('cooldown-active');
      circuitPill.className = 'status-pill override';
      circuitPill.textContent = 'OVERRIDE ACTIVE';
      cooldownBanner.classList.add('hidden');
      stopCooldownCountdown();
    } else {
      circuitCard.classList.remove('cooldown-active');
      circuitPill.className = 'status-pill safe';
      circuitPill.textContent = 'ARMED & NORMAL';
      cooldownBanner.classList.add('hidden');
      stopCooldownCountdown();
    }
  } catch (err) {
    console.error('Failed to fetch circuit breaker:', err);
  }
}

function startCooldownCountdown(untilIso) {
  stopCooldownCountdown();
  if (!untilIso) return;

  const target = new Date(untilIso).getTime();
  const updateTimer = () => {
    const now = Date.now();
    const diff = target - now;
    if (diff <= 0) {
      document.getElementById('cooldownTimerText').textContent = 'Cooldown ending...';
      stopCooldownCountdown();
      fetchCircuitBreakerData();
      return;
    }
    const h = Math.floor(diff / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    const s = Math.floor((diff % 60000) / 1000);
    document.getElementById('cooldownTimerText').textContent =
      `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')} remaining`;
  };

  updateTimer();
  state.cooldownTimerInterval = setInterval(updateTimer, 1000);
}

function stopCooldownCountdown() {
  if (state.cooldownTimerInterval) {
    clearInterval(state.cooldownTimerInterval);
    state.cooldownTimerInterval = null;
  }
}

async function fetchBarsData() {
  try {
    const symbol = state.activeSymbol;
    const timeframe = state.activeTimeframe;
    const res = await fetch(`/api/bars?symbol=${symbol}&timeframe=${timeframe}&limit=60`);
    if (!res.ok) return;
    const data = await res.json();
    state.bars = data.bars || [];

    // Update OHLC Header Summary with latest candle
    if (state.bars.length > 0) {
      const latest = state.bars[state.bars.length - 1];
      const prev = state.bars.length > 1 ? state.bars[state.bars.length - 2] : latest;

      document.getElementById('valOpen').textContent = latest.open.toFixed(2);
      document.getElementById('valHigh').textContent = latest.high.toFixed(2);
      document.getElementById('valLow').textContent = latest.low.toFixed(2);
      document.getElementById('valClose').textContent = latest.close.toFixed(2);

      const chg = latest.close - prev.close;
      const chgPct = (chg / prev.close) * 100;
      const badge = document.getElementById('valChangeBadge');
      badge.textContent = `${chg >= 0 ? '+' : ''}${chg.toFixed(2)} (${chgPct.toFixed(2)}%)`;
      badge.style.color = chg >= 0 ? '#26A69A' : '#EF5350';

      document.getElementById('orderPrice').value = latest.close.toFixed(2);
      document.getElementById('chartBarCount').textContent = `Loaded ${state.bars.length} candles`;
    }

    if (chartRenderer) chartRenderer.render();
  } catch (err) {
    console.error('Failed to fetch bars:', err);
  }
}

async function fetchTradesData() {
  try {
    const res = await fetch('/api/trades');
    if (!res.ok) return;
    const data = await res.json();
    state.trades = data.trades || [];

    const stream = document.getElementById('tradeLogStream');
    document.getElementById('tradesCount').textContent = `${state.trades.length} Total`;

    if (state.trades.length === 0) {
      stream.innerHTML = `<div class="empty-state-text">No trades executed today.</div>`;
      return;
    }

    stream.innerHTML = state.trades
      .slice(-10)
      .reverse()
      .map((t) => {
        const isBuy = t.action === 'BUY';
        const tagClass = isBuy ? 'BUY' : 'SELL';
        const pnl = t.pnl !== undefined ? t.pnl : 0;
        const pnlText = pnl !== 0 ? `<span class="mono ${pnl > 0 ? 'text-bullish' : 'text-bearish'}">${formatCurrency(pnl)}</span>` : '';

        return `
          <div class="trade-item">
            <div class="trade-item-left">
              <span class="trade-action-tag ${tagClass}">${t.action}</span>
              <strong>${t.symbol}</strong>
              <span class="text-muted">${t.quantity} @ ${formatCurrency(t.price)}</span>
            </div>
            <div class="trade-item-right mono">
              ${pnlText}
            </div>
          </div>
        `;
      })
      .join('');
  } catch (err) {
    console.error('Failed to fetch trades:', err);
  }
}

async function fetchPostMortemsData() {
  try {
    const res = await fetch('/api/post-mortems?limit=6');
    if (!res.ok) return;
    const data = await res.json();
    state.postMortems = data.post_mortems || [];

    document.getElementById('postMortemCount').textContent = state.postMortems.length;
    const grid = document.getElementById('postMortemGrid');

    if (state.postMortems.length === 0) {
      grid.innerHTML = `<div class="empty-state-text">No loss post-mortems logged. All executions are operating within safe bounds.</div>`;
      return;
    }

    grid.innerHTML = state.postMortems
      .map((pm) => {
        const lossVal = formatCurrency(pm.loss_amount);
        const tags = (pm.failure_tags || []).map((t) => `<span class="pm-tag">#${t}</span>`).join('');

        return `
          <div class="pm-card">
            <div class="pm-header">
              <span class="pm-symbol">${pm.symbol} • ${pm.strategy_name || 'ORB'}</span>
              <span class="pm-loss-badge">-${lossVal}</span>
            </div>
            <div class="pm-section-block">
              <span class="pm-lbl">ROOT CAUSE</span>
              <p class="pm-text">${pm.root_cause || 'Execution loss triggered auto-analysis.'}</p>
            </div>
            <div class="pm-rule-box">
              <span class="pm-lbl" style="color:#C084FC;">AUTONOMOUS PREVENTATIVE RULE</span>
              <p class="pm-rule-text">"${pm.preventative_rule || 'Enforce stricter stop loss verification.'}"</p>
            </div>
            <div class="pm-tags-row">
              ${tags}
            </div>
          </div>
        `;
      })
      .join('');
  } catch (err) {
    console.error('Failed to fetch post mortems:', err);
  }
}

/* ==========================================================================
   EXECUTION HANDLERS
   ========================================================================== */
async function submitOrder(action) {
  const symbol = document.getElementById('orderSymbol').value.trim().toUpperCase();
  const strategy = document.getElementById('orderStrategy').value;
  const price = parseFloat(document.getElementById('orderPrice').value);
  const quantity = parseInt(document.getElementById('orderQuantity').value, 10);

  if (!symbol || isNaN(price) || isNaN(quantity) || quantity <= 0) {
    showToast('Please enter valid order details', 'error');
    return;
  }

  const feedbackBox = document.getElementById('executionFeedback');
  const feedbackBadge = document.getElementById('feedbackBadge');
  const feedbackMsg = document.getElementById('feedbackMessage');

  feedbackBadge.textContent = 'CHECKING RISK...';
  feedbackBadge.style.color = '#38BDF8';

  try {
    const res = await fetch('/api/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, action, price, quantity, strategy }),
    });

    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`Order filled: ${action} ${quantity} ${symbol} @ $${price.toFixed(2)}`, 'success');
      feedbackBadge.textContent = 'FILLED';
      feedbackBadge.style.color = '#26A69A';
      feedbackMsg.textContent = `Order ${data.order.order_id} filled successfully. Portfolio updated.`;
      refreshAll();
    } else {
      const reason = data.reason || data.error || 'Blocked by risk management';
      showToast(`Order rejected: ${reason}`, 'error');
      feedbackBadge.textContent = 'REJECTED';
      feedbackBadge.style.color = '#EF5350';
      feedbackMsg.textContent = `Guard blocked order: ${reason}`;
    }
  } catch (err) {
    showToast(`Execution error: ${err.message}`, 'error');
    feedbackBadge.textContent = 'ERROR';
    feedbackBadge.style.color = '#EF5350';
  }
}

async function quickExitPosition(symbol, estPrice) {
  const pos = state.positions.find((p) => p.symbol === symbol);
  const qty = pos ? pos.quantity : 10;

  try {
    const res = await fetch('/api/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        symbol,
        action: 'EXIT',
        price: estPrice || 100.0,
        quantity: qty,
        strategy: 'MANUAL',
      }),
    });

    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`Position closed: ${symbol}`, 'success');
      refreshAll();
    } else {
      showToast(`Failed to close position: ${data.reason || data.error}`, 'error');
    }
  } catch (err) {
    showToast(`Exit error: ${err.message}`, 'error');
  }
}

async function toggleCircuitBreakerOverride() {
  const current = state.circuitBreaker ? state.circuitBreaker.manual_override : false;
  const newOverride = !current;

  try {
    const res = await fetch('/api/circuit-breaker/override', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ override: newOverride }),
    });

    const data = await res.json();
    if (res.ok && data.success) {
      showToast(
        newOverride ? 'Manual Override ACTIVATED: Circuit breaker bypassed.' : 'Manual Override DEACTIVATED.',
        newOverride ? 'warning' : 'info'
      );
      fetchCircuitBreakerData();
    }
  } catch (err) {
    showToast(`Override error: ${err.message}`, 'error');
  }
}

async function setExecutionMode(mode) {
  try {
    const res = await fetch('/api/mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
    });

    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`Execution mode switched to: ${mode}`, 'info');
      fetchAccountData();
    }
  } catch (err) {
    showToast(`Mode switch error: ${err.message}`, 'error');
  }
}

/* ==========================================================================
   INITIALIZATION & EVENT BINDINGS
   ========================================================================== */
function refreshAll() {
  fetchAccountData();
  fetchPositionsData();
  fetchCircuitBreakerData();
  fetchBarsData();
  fetchTradesData();
  fetchPostMortemsData();
}

window.addEventListener('DOMContentLoaded', () => {
  chartRenderer = new FinancialChartRenderer('financialChartCanvas');

  // Symbol Selector
  const symbolSelect = document.getElementById('symbolSelect');
  symbolSelect.addEventListener('change', (e) => {
    state.activeSymbol = e.target.value;
    document.getElementById('orderSymbol').value = state.activeSymbol;
    fetchBarsData();
  });

  // Timeframe Buttons
  const tfButtons = document.querySelectorAll('#timeframeSelector .tf-btn');
  tfButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      tfButtons.forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      state.activeTimeframe = btn.dataset.tf;
      fetchBarsData();
    });
  });

  // Chart Type Selector
  const typeButtons = document.querySelectorAll('#chartTypeSelector .type-btn');
  typeButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      typeButtons.forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      state.chartType = btn.dataset.type;
      if (chartRenderer) chartRenderer.render();
    });
  });

  // Order Buttons
  document.getElementById('btnBuyMarket').addEventListener('click', () => submitOrder('BUY'));
  document.getElementById('btnSellMarket').addEventListener('click', () => submitOrder('SELL'));
  document.getElementById('btnExitPosition').addEventListener('click', () => submitOrder('EXIT'));

  // Manual Override Button
  document.getElementById('btnToggleOverride').addEventListener('click', toggleCircuitBreakerOverride);

  // Mode Buttons
  document.getElementById('btnVirtualMode').addEventListener('click', () => setExecutionMode('VIRTUAL'));
  document.getElementById('btnLiveMode').addEventListener('click', () => setExecutionMode('LIVE'));

  // Manual Refresh
  document.getElementById('btnManualRefresh').addEventListener('click', () => {
    showToast('Refreshing live telemetry...', 'info');
    refreshAll();
  });

  // Initial Data Fetch
  refreshAll();

  // Background Poll every 3 seconds
  state.pollInterval = setInterval(refreshAll, 3000);
});
