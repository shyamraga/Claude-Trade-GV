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

const formatTime = (isoString) => {
  if (!isoString) return '--:--:--';
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) {
      return isoString.includes('T') ? isoString.split('T')[1].split('.')[0] : isoString;
    }
    return d.toTimeString().split(' ')[0];
  } catch (e) {
    return isoString;
  }
};

const renderTargetExit = (p) => {
  const sl = p.stop_loss ? `<span class="target-exit-chip sl" title="Stop Loss Trigger">SL: $${Number(p.stop_loss).toFixed(2)}</span>` : '<span class="text-muted" style="font-size:10px;">SL: Auto (2%)</span>';
  const tp = p.take_profit ? `<span class="target-exit-chip tp" title="Take Profit Target">TP: $${Number(p.take_profit).toFixed(2)}</span>` : '<span class="text-muted" style="font-size:10px;">TP: Auto (4%)</span>';
  return `<div class="target-exit-wrap">${sl}${tp}</div>`;
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
    this.rafPending = false;
    this.setupListeners();
  }

  setupListeners() {
    if (!this.canvas) return;

    if (window.ResizeObserver && this.canvas.parentElement) {
      this.resizeObserver = new ResizeObserver(() => {
        this.requestRender();
      });
      this.resizeObserver.observe(this.canvas.parentElement);
    } else {
      window.addEventListener('resize', () => {
        this.requestRender();
      });
    }

    this.canvas.addEventListener('mousemove', (e) => {
      const rect = this.canvas.getBoundingClientRect();
      this.crosshair.active = true;
      this.crosshair.x = e.clientX - rect.left;
      this.crosshair.y = e.clientY - rect.top;
      this.requestRender();
    });

    this.canvas.addEventListener('mouseleave', () => {
      this.crosshair.active = false;
      if (this.tooltip) this.tooltip.classList.add('hidden');
      this.requestRender();
    });
  }

  requestRender() {
    if (this.rafPending) return;
    this.rafPending = true;
    window.requestAnimationFrame(() => {
      this.rafPending = false;
      this.render();
    });
  }

  calculateEMA(period) {
    const bars = state.bars;
    if (!bars || bars.length < period) return [];
    const k = 2 / (period + 1);
    const emaValues = new Array(bars.length).fill(null);
    let ema = bars[0].close;
    emaValues[0] = ema;
    for (let i = 1; i < bars.length; i++) {
      ema = (bars[i].close * k) + (ema * (1 - k));
      emaValues[i] = ema;
    }
    return emaValues;
  }

  resizeCanvas() {
    const parent = this.canvas.parentElement;
    if (!parent) return { width: 800, height: 420 };
    const dpr = window.devicePixelRatio || 1;
    const width = Math.max(300, Math.floor(parent.clientWidth || 800));
    const height = Math.max(260, Math.floor(parent.clientHeight || 420));

    const targetWidth = Math.floor(width * dpr);
    const targetHeight = Math.floor(height * dpr);

    // Only update internal drawing buffer when dimensions actually change
    if (this.canvas.width !== targetWidth || this.canvas.height !== targetHeight) {
      this.canvas.width = targetWidth;
      this.canvas.height = targetHeight;
    }

    // Do NOT set this.canvas.style.width / style.height in JS!
    // CSS rules (#financialChartCanvas { width: 100% !important; height: 100% !important; })
    // control layout dimensions and prevent recursive CSS Grid expansion loops.

    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { width, height };
  }

  render() {
    if (!this.ctx || !state.bars || state.bars.length === 0) return;

    const { width, height } = this.resizeCanvas();
    const ctx = this.ctx;
    const bars = state.bars;

    // Layout configuration
    const padding = { top: 25, right: 85, bottom: 35, left: 20 };
    const chartWidth = Math.max(100, width - padding.left - padding.right);
    const chartHeight = Math.max(100, height - padding.top - padding.bottom);
    const volumeHeight = chartHeight * 0.16;
    const priceChartHeight = chartHeight - volumeHeight - 18;

    // Helper for formatting prices according to asset scale
    const formatPrice = (val) => {
      if (val === undefined || val === null || isNaN(val)) return '0.00';
      if (val >= 1000) return val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      if (val < 0.1) return val.toFixed(4);
      return val.toFixed(2);
    };

    // Background fill with subtle OLED gradient
    const bgGrad = ctx.createLinearGradient(0, 0, 0, height);
    bgGrad.addColorStop(0, '#040711');
    bgGrad.addColorStop(1, '#020307');
    ctx.fillStyle = bgGrad;
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
    const candleWidth = Math.max(3, (chartWidth / bars.length) * 0.68);

    // Draw Price Horizontal Grid Lines & Y-Axis labels
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

      ctx.fillStyle = '#94A3B8';
      ctx.fillText(formatPrice(p), width - padding.right + 8, y + 3);
    }

    // Draw X-Axis Timestamp Ticks & Vertical Grid Lines
    const tickInterval = Math.max(1, Math.floor(bars.length / 6));
    ctx.textAlign = 'center';
    ctx.fillStyle = '#64748B';
    ctx.font = '10px "JetBrains Mono", monospace';

    for (let i = 0; i < bars.length; i += tickInterval) {
      const x = getX(i);
      const b = bars[i];
      let timeLabel = '';
      if (b.timestamp) {
        if (state.activeTimeframe === '1d') {
          const parts = b.timestamp.split('T')[0].split('-');
          timeLabel = parts.length >= 3 ? `${parts[1]}/${parts[2]}` : b.timestamp.split('T')[0];
        } else {
          timeLabel = b.timestamp.includes('T') ? b.timestamp.split('T')[1].substring(0, 5) : b.timestamp;
        }
      }

      // Vertical subtle grid
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.03)';
      ctx.beginPath();
      ctx.moveTo(x, padding.top);
      ctx.lineTo(x, height - padding.bottom);
      ctx.stroke();

      // Timestamp label
      ctx.fillText(timeLabel, x, height - padding.bottom + 16);
    }

    // Draw Volume Bars
    const volBaseY = height - padding.bottom;
    bars.forEach((b, idx) => {
      const x = getX(idx);
      const isUp = b.close >= b.open;
      const vHeight = maxVolume > 0 ? (b.volume / maxVolume) * volumeHeight : 0;
      const y = volBaseY - vHeight;

      ctx.fillStyle = isUp ? 'rgba(0, 255, 136, 0.28)' : 'rgba(255, 51, 102, 0.28)';
      ctx.fillRect(x - candleWidth / 2, y, candleWidth, vHeight);
    });

    // Draw Price Series (Candlestick or Line View)
    if (state.chartType === 'candle') {
      bars.forEach((b, idx) => {
        const x = getX(idx);
        const openY = getY(b.open);
        const closeY = getY(b.close);
        const highY = getY(b.high);
        const lowY = getY(b.low);
        const isUp = b.close >= b.open;
        const color = isUp ? '#00FF88' : '#FF3366';

        // Draw Wick
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(x, highY);
        ctx.lineTo(x, lowY);
        ctx.stroke();

        // Draw Candle Body with rounded finish
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

      ctx.strokeStyle = '#00F0FF';
      ctx.lineWidth = 2;
      ctx.stroke();

      // Cyber Cyan Gradient Fill
      ctx.lineTo(getX(bars.length - 1), priceChartHeight + padding.top);
      ctx.lineTo(getX(0), priceChartHeight + padding.top);
      ctx.closePath();
      const grad = ctx.createLinearGradient(0, padding.top, 0, priceChartHeight + padding.top);
      grad.addColorStop(0, 'rgba(0, 240, 255, 0.22)');
      grad.addColorStop(1, 'rgba(0, 240, 255, 0.0)');
      ctx.fillStyle = grad;
      ctx.fill();
    }

    // Draw Fast EMA (9) and Slow EMA (21) technical overlays
    const ema9 = this.calculateEMA(9);
    const ema21 = this.calculateEMA(21);

    if (ema9.length === bars.length) {
      ctx.beginPath();
      ctx.strokeStyle = '#00F0FF';
      ctx.lineWidth = 1.5;
      let started = false;
      ema9.forEach((val, idx) => {
        if (val !== null) {
          const x = getX(idx);
          const y = getY(val);
          if (!started) { ctx.moveTo(x, y); started = true; }
          else { ctx.lineTo(x, y); }
        }
      });
      ctx.stroke();
    }

    if (ema21.length === bars.length) {
      ctx.beginPath();
      ctx.strokeStyle = '#F59E0B';
      ctx.lineWidth = 1.5;
      let started = false;
      ema21.forEach((val, idx) => {
        if (val !== null) {
          const x = getX(idx);
          const y = getY(val);
          if (!started) { ctx.moveTo(x, y); started = true; }
          else { ctx.lineTo(x, y); }
        }
      });
      ctx.stroke();
    }

    // Draw Current Price Dashed Guide Line & Price Badge
    const latestBar = bars[bars.length - 1];
    if (latestBar) {
      const latestY = getY(latestBar.close);
      const isUp = latestBar.close >= latestBar.open;
      const lineColor = isUp ? 'rgba(0, 255, 136, 0.7)' : 'rgba(255, 51, 102, 0.7)';

      ctx.strokeStyle = lineColor;
      ctx.setLineDash([4, 4]);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(padding.left, latestY);
      ctx.lineTo(width - padding.right, latestY);
      ctx.stroke();
      ctx.setLineDash([]);

      // Price Tag on Right Margin
      ctx.fillStyle = isUp ? '#00FF88' : '#FF3366';
      ctx.fillRect(width - padding.right + 2, latestY - 9, 78, 18);
      ctx.fillStyle = '#000000';
      ctx.font = 'bold 10px "JetBrains Mono", monospace';
      ctx.textAlign = 'left';
      ctx.fillText(`$${formatPrice(latestBar.close)}`, width - padding.right + 5, latestY + 4);
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
          const diffPct = hoveredBar.open > 0 ? (diff / hoveredBar.open) * 100 : 0;
          this.tooltip.innerHTML = `
            <div style="font-weight:700; color:#00F0FF; margin-bottom:4px; font-family:'JetBrains Mono';">${hoveredBar.timestamp.replace('T', ' ')}</div>
            <div>O: <strong>$${formatPrice(hoveredBar.open)}</strong></div>
            <div>H: <strong>$${formatPrice(hoveredBar.high)}</strong></div>
            <div>L: <strong>$${formatPrice(hoveredBar.low)}</strong></div>
            <div>C: <strong style="color:${isUp ? '#00FF88' : '#FF3366'}">$${formatPrice(hoveredBar.close)} (${diff >= 0 ? '+' : ''}${diffPct.toFixed(2)}%)</strong></div>
            <div>Vol: <strong>${Number(hoveredBar.volume).toLocaleString()}</strong></div>
          `;
          this.tooltip.style.left = `${Math.min(width - 170, Math.max(10, snappedX + 15))}px`;
          this.tooltip.style.top = `${Math.min(height - 140, Math.max(10, this.crosshair.y - 40))}px`;
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
      tbody.innerHTML = `<tr><td colspan="10" class="text-center text-muted py-6">No open positions. Ready to trade.</td></tr>`;
      return;
    }

    tbody.innerHTML = state.positions
      .map((p) => {
        const isProfit = (p.unrealized_pnl || 0) >= 0;
        const pnlClass = isProfit ? 'positive' : 'negative';
        const mktVal = (p.quantity || 0) * (p.current_price || p.entry_price || 0);
        const isShort = (p.side || '').toUpperCase() === 'SHORT';
        const sideTagClass = isShort ? 'SELL' : 'BUY';
        const sideText = isShort ? 'SHORT' : 'LONG';

        return `
          <tr>
            <td style="font-weight:700;">${p.symbol}</td>
            <td><span class="trade-action-tag ${sideTagClass}">${sideText}</span></td>
            <td><span class="timestamp-chip">${formatTime(p.opened_at)}</span></td>
            <td>${renderTargetExit(p)}</td>
            <td class="text-right mono">${p.quantity}</td>
            <td class="text-right mono">${formatCurrency(p.entry_price)}</td>
            <td class="text-right mono">${formatCurrency(p.current_price)}</td>
            <td class="text-right mono">${formatCurrency(mktVal)}</td>
            <td class="text-right mono pnl-text ${pnlClass}">
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
    const barCountEl = document.getElementById('chartBarCount');
    if (barCountEl && (!state.bars || state.bars.length === 0)) {
      barCountEl.textContent = `Fetching live ${symbol} stream...`;
    }

    const res = await fetch(`/api/bars?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}&limit=60`);
    if (!res.ok) return;
    const data = await res.json();

    // Guard against race conditions when switching symbols quickly
    if (data.symbol && data.symbol !== state.activeSymbol) {
      return;
    }

    state.bars = data.bars || [];

    // Helper for formatting prices according to asset scale
    const formatPriceVal = (val) => {
      if (val === undefined || val === null || isNaN(val)) return '---';
      if (val >= 1000) {
        return val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      } else if (val < 0.1) {
        return val.toFixed(4);
      }
      return val.toFixed(2);
    };

    // Update OHLC Header Summary with latest candle
    if (state.bars.length > 0) {
      const latest = state.bars[state.bars.length - 1];
      const prev = state.bars.length > 1 ? state.bars[state.bars.length - 2] : latest;

      document.getElementById('valOpen').textContent = formatPriceVal(latest.open);
      document.getElementById('valHigh').textContent = formatPriceVal(latest.high);
      document.getElementById('valLow').textContent = formatPriceVal(latest.low);
      document.getElementById('valClose').textContent = formatPriceVal(latest.close);

      const chg = latest.close - prev.close;
      const chgPct = prev.close > 0 ? (chg / prev.close) * 100 : 0;
      const badge = document.getElementById('valChangeBadge');
      badge.textContent = `${chg >= 0 ? '+' : ''}${formatPriceVal(chg)} (${chgPct.toFixed(2)}%)`;
      badge.style.color = chg >= 0 ? '#26A69A' : '#EF5350';

      const orderPriceInput = document.getElementById('orderPrice');
      if (orderPriceInput) {
        orderPriceInput.value = latest.close >= 1 ? latest.close.toFixed(2) : latest.close.toFixed(4);
      }
      if (barCountEl) {
        barCountEl.textContent = `${symbol} · ${state.bars.length} candles · Real-Time`;
      }
    }

    if (chartRenderer) chartRenderer.requestRender();
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
    const tradesCountEl = document.getElementById('tradesCount');
    if (tradesCountEl) tradesCountEl.textContent = `${state.trades.length} Total`;

    // Compute Summary Realized P&L, Win/Loss rate, and average
    let totalRealized = 0;
    let wins = 0;
    let losses = 0;
    state.trades.forEach(t => {
      const pnl = t.pnl !== undefined ? t.pnl : 0;
      totalRealized += pnl;
      if (pnl > 0) wins++;
      else if (pnl < 0) losses++;
    });

    const totalClosed = state.trades.length;
    const winRate = totalClosed > 0 ? ((wins / totalClosed) * 100).toFixed(1) : '0.0';
    const avgTrade = totalClosed > 0 ? (totalRealized / totalClosed) : 0;

    const elRealized = document.getElementById('cardRealizedPnl');
    if (elRealized) {
      elRealized.textContent = formatCurrency(totalRealized);
      elRealized.style.color = totalRealized >= 0 ? '#26A69A' : '#EF5350';
    }

    const tagRealized = document.getElementById('realizedPnlTag');
    if (tagRealized) {
      tagRealized.textContent = `${totalClosed} CLOSED`;
      tagRealized.className = `stat-tag ${totalRealized >= 0 ? 'tag-green' : 'tag-amber'}`;
    }

    const elWinLoss = document.getElementById('cardWinLossRate');
    if (elWinLoss) {
      elWinLoss.textContent = `${wins}W - ${losses}L (${winRate}%)`;
      elWinLoss.className = `delta-badge ${wins >= losses && totalClosed > 0 ? 'positive' : (losses > wins ? 'negative' : 'neutral')}`;
    }

    const elAvg = document.getElementById('cardAvgTradeFootnote');
    if (elAvg) {
      elAvg.textContent = `Avg: ${formatCurrency(avgTrade)} / trade`;
    }

    if (state.trades.length === 0) {
      if (stream) stream.innerHTML = `<div class="empty-state-text">No trades executed today.</div>`;
      return;
    }

    if (stream) {
      stream.innerHTML = state.trades
        .slice(-10)
        .reverse()
        .map((t) => {
          const isBuy = (t.side || t.action) === 'BUY';
          const tagClass = isBuy ? 'BUY' : 'SELL';
          const sideText = isBuy ? 'LONG' : 'SHORT';
          const pnl = t.pnl !== undefined ? t.pnl : 0;
          const pnlText = pnl !== 0 ? `<span class="mono ${pnl > 0 ? 'text-bullish' : 'text-bearish'}">${formatCurrency(pnl)}</span>` : '<span class="text-muted">$0.00</span>';
          const reasonClass = t.reason || 'SIGNAL_EXIT';
          const reasonLabel = (t.reason || 'EXIT').replace('_', ' ');
          const exitPrice = t.exit_price || t.entry_price || t.price || 0;

          return `
            <div class="trade-item">
              <div class="trade-item-left">
                <span class="trade-action-tag ${tagClass}">${sideText}</span>
                <strong>${t.symbol}</strong>
                <span class="text-muted">${t.quantity} @ ${formatCurrency(exitPrice)}</span>
                <span class="trade-reason-chip ${reasonClass}">${reasonLabel}</span>
              </div>
              <div class="trade-item-right mono text-right">
                <div>${pnlText}</div>
                <div class="timestamp-chip" title="Opened ➔ Closed">${formatTime(t.entry_time)} ➔ ${formatTime(t.exit_time)}</div>
              </div>
            </div>
          `;
        })
        .join('');
    }
  } catch (err) {
    console.error('Failed to fetch trades:', err);
  }
}

async function fetchPostMortemsData() {
  try {
    const res = await fetch('/api/post-mortems?limit=50');
    if (!res.ok) return;
    const data = await res.json();
    state.postMortems = data.post_mortems || [];

    const totalCount = data.total_count !== undefined ? data.total_count : state.postMortems.length;
    const pmCountEl = document.getElementById('postMortemCount');
    if (pmCountEl) {
      pmCountEl.textContent = `${totalCount}`;
    }
    const auditTag = document.getElementById('postMortemAuditTag');
    if (auditTag) {
      auditTag.textContent = `${totalCount} AUDITED RULES`;
    }
    const grid = document.getElementById('postMortemGrid');
    if (!grid) return;

    if (state.postMortems.length === 0) {
      grid.innerHTML = `<div class="empty-state-text">No trade debriefs logged yet. Closed trades will appear here automatically.</div>`;
      return;
    }

    grid.innerHTML = state.postMortems
      .map((pm) => {
        const isWin = pm.outcome === 'WIN' || (pm.pnl !== undefined && pm.pnl > 0);
        const cardClass = isWin ? 'pm-card win' : 'pm-card';
        const pnlVal = pm.pnl !== undefined ? pm.pnl : (isWin ? pm.loss_amount : -pm.loss_amount);
        const badgeClass = isWin ? 'pm-win-badge' : 'pm-loss-badge';
        const badgeText = isWin ? `+${formatCurrency(Math.abs(pnlVal))}` : `-${formatCurrency(Math.abs(pnlVal))}`;
        const outcomeTag = isWin ? '<span class="status-pill safe" style="font-size:9px;padding:2px 6px;">WIN DEBRIEF</span>' : '<span class="status-pill warning" style="font-size:9px;padding:2px 6px;">LOSS POST-MORTEM</span>';
        const rootLbl = isWin ? 'SETUP VALIDATION' : 'ROOT CAUSE';
        const ruleLbl = isWin ? 'VALIDATED SETUP RULE' : 'AUTONOMOUS PREVENTATIVE RULE';

        const riskTagKeys = ['bull-trap', 'bear-trap', 'failed-continuation', 'short-squeeze', 'trend-exhaustion', 'falling-knife', 'melt-up-trap', 'ma-lag-whipsaw', 'pullback-whipsaw', 'short-the-hole'];
        const tags = (pm.tags || pm.failure_tags || []).map((t) => {
          const tLower = t.toLowerCase();
          const isRisk = riskTagKeys.includes(tLower);
          const cls = isRisk ? 'pm-tag pm-tag-risk' : (tLower === 'crypto' ? 'pm-tag pm-tag-crypto' : 'pm-tag');
          return `<span class="${cls}">#${t}</span>`;
        }).join('');

        const entryP = pm.entry_price ? `$${Number(pm.entry_price).toFixed(2)}` : '--';
        const exitP = pm.exit_price ? `$${Number(pm.exit_price).toFixed(2)}` : '--';
        const durMin = (pm.entry_time && pm.exit_time)
          ? Math.max(1, Math.round((new Date(pm.exit_time) - new Date(pm.entry_time)) / 60000))
          : null;
        const durText = durMin !== null ? ` • Hold: ${durMin}m` : '';

        return `
          <div class="${cardClass}">
            <div class="pm-header">
              <div class="flex-row items-center gap-2">
                <span class="pm-symbol">${pm.symbol} • ${pm.strategy_name || 'ORB'}</span>
                ${outcomeTag}
              </div>
              <span class="${badgeClass}">${badgeText}</span>
            </div>
            <div class="pm-sub-meta text-muted" style="font-size:10px; margin-top:-4px;">
              <span>${entryP} ➔ ${exitP}${durText}</span>
            </div>
            <div class="pm-section-block">
              <span class="pm-lbl">${rootLbl}</span>
              <p class="pm-text">${pm.root_cause || (isWin ? 'Execution achieved take-profit or positive momentum.' : 'Execution loss triggered auto-analysis.')}</p>
            </div>
            <div class="pm-rule-box">
              <span class="pm-lbl" style="color:${isWin ? '#26A69A' : '#C084FC'};">${ruleLbl}</span>
              <p class="pm-rule-text">"${pm.preventative_rule || (isWin ? 'Continue executing validated setup when volume confirms.' : 'Enforce stricter stop loss verification.')}"</p>
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

// Global aliases for button click handlers
window.quickExitPosition = quickExitPosition;
window.exitPosition = function(symbol) {
  return quickExitPosition(symbol);
};

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
   LIVE TRADE VIEW — TAB SWITCHING, SCANNER LOGS, LIVE METRICS
   ========================================================================== */

let liveTradeState = {
  autoScroll: true,
  lastLogCount: 0,
  scannerPollInterval: null,
  activeTab: 'tabOverview',
};

function switchTab(tabName) {
  const overviewPane = document.getElementById('tabOverviewContent');
  const livePane = document.getElementById('tabLiveTradeContent');
  const swarmPane = document.getElementById('tabAgentSwarmContent');
  const btnOverview = document.getElementById('btnTabOverview');
  const btnLive = document.getElementById('btnTabLiveTrade');
  const btnSwarm = document.getElementById('btnTabAgentSwarm');

  // Reset all panels and buttons
  overviewPane.classList.add('hidden');
  overviewPane.classList.remove('active');
  livePane.classList.add('hidden');
  livePane.classList.remove('active');
  if (swarmPane) {
    swarmPane.classList.add('hidden');
    swarmPane.classList.remove('active');
  }

  btnOverview.classList.remove('active');
  btnLive.classList.remove('active');
  if (btnSwarm) btnSwarm.classList.remove('active');

  if (tabName === 'tabOverview') {
    overviewPane.classList.add('active');
    overviewPane.classList.remove('hidden');
    btnOverview.classList.add('active');

    // Re-render canvas immediately when switching back to Overview
    window.requestAnimationFrame(() => {
      if (chartRenderer) chartRenderer.render();
    });
  } else if (tabName === 'tabLiveTrade') {
    livePane.classList.add('active');
    livePane.classList.remove('hidden');
    btnLive.classList.add('active');
    fetchScannerLogs();
    updateLiveMetrics();
    updateLivePositions();
  } else if (tabName === 'tabAgentSwarm') {
    if (swarmPane) {
      swarmPane.classList.add('active');
      swarmPane.classList.remove('hidden');
    }
    if (btnSwarm) btnSwarm.classList.add('active');
    fetchAgentSwarmData();
  }
  liveTradeState.activeTab = tabName;
}

/* ==========================================================================
   AGENT SWARM HUD TELEMETRY FETCHER
   ========================================================================== */
async function fetchAgentSwarmData() {
  try {
    const res = await fetch('/api/agents');
    if (!res.ok) return;
    const data = await res.json();

    // 1. Supervisor Stats
    const elActive = document.getElementById('swarmActiveCount');
    if (elActive && data.total_sub_agents) {
      elActive.textContent = `${data.total_sub_agents} / ${data.total_sub_agents} ONLINE`;
    }
    const elRuns = document.getElementById('swarmTotalRuns');
    if (elRuns) {
      elRuns.textContent = (data.total_swarm_runs || 0).toLocaleString();
    }

    // 2. Dynamic Universe Batch Scanner Telemetry
    const scan = data.scan_progress || {};
    const isScanning = Boolean(scan.is_scanning);

    // 2a. Beacon Animation
    const beaconPing = document.getElementById('scanBeaconPing');
    const beaconDot = document.getElementById('scanBeaconDot');
    if (beaconPing) {
      if (isScanning) {
        beaconPing.style.display = 'block';
        beaconPing.classList.add('active');
      } else {
        beaconPing.classList.remove('active');
      }
    }
    if (beaconDot) {
      beaconDot.style.background = isScanning ? '#00e5ff' : '#26A69A';
    }

    // 2b. Status Badge & Cycle Tag
    const scanStatusBadge = document.getElementById('scanStatusBadge');
    if (scanStatusBadge) {
      if (isScanning) {
        scanStatusBadge.textContent = 'SCANNING BATCH';
        scanStatusBadge.className = 'scan-status-badge mono scanning';
      } else {
        scanStatusBadge.textContent = 'CYCLE COMPLETED - STANDBY';
        scanStatusBadge.className = 'scan-status-badge mono idle';
      }
    }

    const scanCycleTag = document.getElementById('scanCycleTag');
    if (scanCycleTag) {
      scanCycleTag.textContent = `CYCLE #${scan.cycle_number || 1}`;
    }

    // 2c. Target Symbol & Elapsed
    const scanCurrentTarget = document.getElementById('scanCurrentTarget');
    if (scanCurrentTarget) {
      const curSym = scan.current_symbol || (isScanning ? 'EVALUATING...' : 'IDLE');
      scanCurrentTarget.textContent = curSym;
      scanCurrentTarget.className = isScanning ? 'text-cyan scanning-pulse' : 'text-cyan';
    }

    const scanElapsedText = document.getElementById('scanElapsedText');
    if (scanElapsedText) {
      const elapsed = typeof scan.elapsed_seconds === 'number' ? scan.elapsed_seconds : 0.0;
      scanElapsedText.textContent = `${elapsed.toFixed(1)}s elapsed`;
    }

    // 2d. Evaluated Count & Countdown
    const scanCountVal = document.getElementById('scanCountVal');
    if (scanCountVal) {
      const evalCount = scan.evaluated_count || 0;
      const totalSyms = scan.total_symbols || 0;
      scanCountVal.textContent = `${evalCount} / ${totalSyms}`;
    }

    const scanNextCountdown = document.getElementById('scanNextCountdown');
    if (scanNextCountdown) {
      if (isScanning) {
        scanNextCountdown.textContent = 'ACTIVE';
        scanNextCountdown.className = 'countdown-val text-cyan';
      } else {
        const nextSec = scan.next_scan_seconds !== undefined ? scan.next_scan_seconds : '--';
        scanNextCountdown.textContent = `${nextSec}s`;
        scanNextCountdown.className = 'countdown-val text-accent';
      }
    }

    // 2e. Animated Progress Bar Strip & Percentage
    const scanProgressFill = document.getElementById('scanProgressFill');
    const scanProgressPct = document.getElementById('scanProgressPct');
    const pct = typeof scan.progress_pct === 'number' ? Math.min(100, Math.max(0, scan.progress_pct)) : 0;

    if (scanProgressFill) {
      scanProgressFill.style.width = `${pct}%`;
      if (isScanning) {
        scanProgressFill.classList.add('animating');
      } else {
        scanProgressFill.classList.remove('animating');
      }
    }

    if (scanProgressPct) {
      scanProgressPct.textContent = `${pct.toFixed(1)}% COMPLETE`;
    }

    // 2f. Top Swarm Pick Banner
    const scanTopPickBanner = document.getElementById('scanTopPickBanner');
    if (scanTopPickBanner) {
      if (scan.top_swarm_setup && scan.top_swarm_setup.symbol) {
        const pick = scan.top_swarm_setup;
        const conf = Math.round((pick.confidence || 0) * 100);
        const act = (pick.action || 'HOLD').toUpperCase();
        scanTopPickBanner.innerHTML = `TOP SWARM PICK: <strong class="text-gold">${pick.symbol}</strong> <span class="sig-action-badge ${act} mono">${act}</span> <span class="mono text-cyan">${conf}% CONF</span>`;
      } else {
        scanTopPickBanner.innerHTML = `TOP SWARM PICK: <strong class="text-gold">${isScanning ? 'SCANNING UNIVERSE...' : 'AWAITING NEXT CYCLE'}</strong>`;
      }
    }

    // 3. Individual Sub-Agents
    const agents = data.agents || {};
    let totalLatency = 0;
    let latencyCount = 0;

    for (const [aid, info] of Object.entries(agents)) {
      // Prioritize top conviction signal across the universe batch
      const peakSig = info.top_signal || info.last_signal || (info.activity_log && info.activity_log.length > 0 ? info.activity_log[0] : null);
      const liveSig = info.last_signal || peakSig;

      const elLat = document.getElementById(`lat-${aid}`);
      const elAct = document.getElementById(`act-${aid}`);
      const elBar = document.getElementById(`confBar-${aid}`);
      const elConf = document.getElementById(`confVal-${aid}`);
      const elReason = document.getElementById(`reason-${aid}`);
      const elEvalTarget = document.getElementById(`evalTarget-${aid}`);
      const elEvalVerdict = document.getElementById(`evalVerdict-${aid}`);
      const elEvalRow = document.getElementById(`evalRow-${aid}`);

      if (liveSig && liveSig.latency_ms !== undefined) {
        totalLatency += liveSig.latency_ms;
        latencyCount++;
        if (elLat) elLat.textContent = `${Number(liveSig.latency_ms).toFixed(2)} ms`;
      }

      // Live Symbol Scanning Stream per Sub-Agent Card
      if (liveSig) {
        if (elEvalTarget) {
          elEvalTarget.textContent = liveSig.symbol || '--';
        }
        if (elEvalVerdict) {
          const act = (liveSig.action || 'HOLD').toUpperCase();
          elEvalVerdict.textContent = act;
          elEvalVerdict.className = `eval-verdict ${act}`;
        }
        if (elEvalRow) {
          if (isScanning || info.is_evaluating) {
            elEvalRow.classList.add('scanning');
          } else {
            elEvalRow.classList.remove('scanning');
          }
        }
      }

      // Peak Conviction Setup Card Display
      if (peakSig) {
        if (elAct) {
          const act = (peakSig.action || 'HOLD').toUpperCase();
          elAct.textContent = `${peakSig.symbol ? peakSig.symbol + ': ' : ''}${act}`;
          elAct.className = `sig-action-badge mono ${act}`;
        }

        const confPct = Math.round((peakSig.confidence || 0) * 100);
        if (elBar) elBar.style.width = `${confPct}%`;
        if (elConf) elConf.textContent = `${confPct}%`;
        if (elReason && peakSig.reason) elReason.textContent = peakSig.reason;

        const m = peakSig.metrics || (liveSig ? liveSig.metrics : {}) || {};
        if (aid === 'trader-timemachine') {
          const elEff = document.getElementById('mEff-trader-timemachine');
          const elReg = document.getElementById('mRegime-trader-timemachine');
          if (elEff && m.efficiency_ratio !== undefined) elEff.textContent = Number(m.efficiency_ratio).toFixed(3);
          if (elReg && m.regime) elReg.textContent = m.regime;
        } else if (aid === 'trader-analyst') {
          const elRsi = document.getElementById('mRsi-trader-analyst');
          const elVol = document.getElementById('mVol-trader-analyst');
          if (elRsi && m.rsi_14 !== undefined) elRsi.textContent = Number(m.rsi_14).toFixed(1);
          if (elVol && m.vol_ratio !== undefined) elVol.textContent = `${Number(m.vol_ratio).toFixed(2)}x`;
        } else if (aid === 'trader-entry') {
          const elVwap = document.getElementById('mVwap-trader-entry');
          const elOpt = document.getElementById('mOptPrice-trader-entry');
          if (elVwap && m.vwap_dist_pct !== undefined) elVwap.textContent = `${Number(m.vwap_dist_pct).toFixed(2)}%`;
          if (elOpt && m.optimal_entry_price !== undefined) elOpt.textContent = `$${Number(m.optimal_entry_price).toFixed(2)}`;
        } else if (aid === 'trader-exit') {
          const elAtr = document.getElementById('mAtr-trader-exit');
          const elStop = document.getElementById('mStopDist-trader-exit');
          if (elAtr && m.atr !== undefined) elAtr.textContent = `$${Number(m.atr).toFixed(2)}`;
          if (elStop && m.trailing_stop_dist !== undefined) elStop.textContent = `$${Number(m.trailing_stop_dist).toFixed(2)}`;
        } else if (aid === 'trader-news') {
          const elSent = document.getElementById('mSent-trader-news');
          const elBias = document.getElementById('mBias-trader-news');
          if (elSent && m.sentiment_score !== undefined) elSent.textContent = Number(m.sentiment_score).toFixed(2);
          if (elBias && m.catalyst) elBias.textContent = m.catalyst;
        } else if (aid === 'trader-pelosi') {
          const elPelosi = document.getElementById('mPelosi-trader-pelosi');
          const elDark = document.getElementById('mDarkPool-trader-pelosi');
          if (elPelosi && m.smart_money_bias !== undefined) elPelosi.textContent = m.smart_money_bias;
          if (elDark && m.dark_pool_volume_spike !== undefined) elDark.textContent = m.dark_pool_volume_spike ? 'DETECTED' : 'NORMAL';
        }
      }

      // 2b. Live Hover Process Inspector Popover Audit Log
      const popoverList = document.getElementById(`popoverLogs-${aid}`);
      const popoverTotal = document.getElementById(`popoverTotal-${aid}`);
      const totalAnalyses = info.total_analyses || (info.activity_log ? info.activity_log.length : 0);
      if (popoverTotal) popoverTotal.textContent = totalAnalyses;

      if (popoverList && info.activity_log && info.activity_log.length > 0) {
        popoverList.innerHTML = info.activity_log.slice(0, 15).map(item => {
          const act = item.action || 'HOLD';
          const sym = item.symbol || 'N/A';
          const conf = Math.round((item.confidence || 0) * 100);
          const lat = item.latency_ms !== undefined ? `${Number(item.latency_ms).toFixed(1)}ms` : '--';
          const time = formatTime(item.timestamp);
          const reason = item.reason || 'Telemetry snapshot recorded';
          return `
            <div class="popover-log-entry">
              <div class="log-entry-top">
                <span class="log-sym">${sym}</span>
                <span class="log-act-badge ${act}">${act}</span>
              </div>
              <div class="log-entry-metrics">
                <span>Conf: <strong>${conf}%</strong></span>
                <span>Lat: <strong>${lat}</strong></span>
                <span>${time}</span>
              </div>
              <div class="log-entry-reason" title="${reason}">${reason}</div>
            </div>
          `;
        }).join('');
      } else if (popoverList && (!info.activity_log || info.activity_log.length === 0)) {
        popoverList.innerHTML = '<div class="text-muted" style="font-size: 10px; padding: 12px; text-align: center;">Streaming live process evaluations...</div>';
      }
    }

    const elAvgLat = document.getElementById('swarmAvgLatency');
    if (elAvgLat && latencyCount > 0) {
      elAvgLat.textContent = `${(totalLatency / latencyCount).toFixed(2)} ms`;
    }

    // 3. Consensus Arbitrations Stream
    const elConsensusList = document.getElementById('swarmConsensusList');
    if (elConsensusList && data.recent_reports && data.recent_reports.length > 0) {
      elConsensusList.innerHTML = data.recent_reports.slice().reverse().map(rep => {
        const votes = rep.agent_signals || {};
        const voteChips = Object.entries(votes).map(([aid, sig]) => {
          const shortName = aid.replace('trader-', '');
          const act = sig.action || 'HOLD';
          return `<span class="consensus-vote-chip ${act}">${shortName}: ${act}</span>`;
        }).join('');

        const timeStr = rep.timestamp ? new Date(rep.timestamp).toLocaleTimeString() : '--:--:--';
        const confPct = Math.round((rep.confidence || 0) * 100);
        const agreementPct = Math.round((rep.consensus_strength || 0) * 100);

        return `
          <div class="consensus-item">
            <div class="consensus-item-header">
              <div class="consensus-symbol-wrap">
                <span class="consensus-symbol mono">${rep.symbol}</span>
                <span class="consensus-decision ${rep.action}">${rep.action}</span>
                <span class="text-muted" style="font-size:10px;">${rep.executive_summary || ''}</span>
              </div>
              <div class="consensus-meta-right mono">
                <span title="Consensus Agreement">${agreementPct}% Agreement</span>
                <span class="text-accent" title="Swarm Confidence">${confPct}% Conf</span>
                <span class="text-muted">${timeStr}</span>
              </div>
            </div>
            <div class="consensus-votes-row">
              <span class="sup-lbl" style="margin-right:4px;">SUB-AGENT VOTES:</span>
              ${voteChips}
            </div>
          </div>
        `;
      }).join('');
    }
  } catch (err) {
    console.warn('Failed to fetch agent swarm telemetry:', err);
  }
}

/* ==========================================================================
   GLOBAL MARKET RADAR & TIMEZONE ARBITRATION
   ========================================================================== */
function updateTimezoneRadarClocks() {
  const now = new Date();

  // 1. Operator Local Time
  const localTimeStr = now.toLocaleTimeString('en-US', { hour12: false });
  let localTzName = 'LOCAL';
  try {
    localTzName = Intl.DateTimeFormat().resolvedOptions().timeZone.toUpperCase();
  } catch (e) {}
  const elOpTime = document.getElementById('radarOperatorTime');
  const elOpTz = document.getElementById('radarOperatorTz');
  if (elOpTime) elOpTime.textContent = localTimeStr;
  if (elOpTz) elOpTz.textContent = localTzName;

  // 2. US Market Clock (America/New_York)
  try {
    const usTimeStr = now.toLocaleTimeString('en-US', {
      timeZone: 'America/New_York',
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
    const elUs = document.getElementById('radarClockUS');
    if (elUs) elUs.textContent = `${usTimeStr} ET`;

    // Fast client-side session evaluation for US markets (09:30 - 16:00 ET, Mon-Fri)
    const usDateStr = now.toLocaleDateString('en-US', { timeZone: 'America/New_York', weekday: 'short' });
    const isWeekend = usDateStr === 'Sat' || usDateStr === 'Sun';
    const parts = usTimeStr.split(':').map(Number);
    const totalMinutes = parts[0] * 60 + parts[1];
    const isRegularHours = !isWeekend && totalMinutes >= (9 * 60 + 30) && totalMinutes < (16 * 60);

    if (!state.hasAuthoritativeMarketSummary) {
      const pill = document.getElementById('radarPillUS');
      const text = document.getElementById('radarStatusTextUS');
      const card = document.getElementById('radarCardUS');
      const detail = document.getElementById('radarDetailUS');

      if (isRegularHours) {
        if (pill) pill.className = 'radar-status-pill open';
        if (text) text.textContent = 'OPEN';
        if (card) card.classList.add('session-open');
        if (detail) detail.textContent = `US Market is OPEN (${usTimeStr} ET). Closes at 16:00 ET.`;
      } else {
        const isPre = !isWeekend && totalMinutes >= (4 * 60) && totalMinutes < (9 * 60 + 30);
        if (pill) pill.className = `radar-status-pill ${isPre ? 'pre' : 'closed'}`;
        if (text) text.textContent = isPre ? 'PRE-MARKET' : 'CLOSED';
        if (card) card.classList.remove('session-open');
      }
    }
  } catch (e) {}

  // 3. Indian Market Clock (Asia/Kolkata)
  try {
    const inTimeStr = now.toLocaleTimeString('en-US', {
      timeZone: 'Asia/Kolkata',
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
    const elIn = document.getElementById('radarClockIN');
    if (elIn) elIn.textContent = `${inTimeStr} IST`;
  } catch (e) {}

  // 4. Crypto Market Clock (UTC)
  try {
    const utcTimeStr = now.toLocaleTimeString('en-US', {
      timeZone: 'UTC',
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
    const elCrypto = document.getElementById('radarClockCrypto');
    if (elCrypto) elCrypto.textContent = `${utcTimeStr} UTC`;
  } catch (e) {}

  // 5. Metals Market Clock (America/New_York - CME Globex)
  try {
    const metalsTimeStr = now.toLocaleTimeString('en-US', {
      timeZone: 'America/New_York',
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
    const elMetals = document.getElementById('radarClockMetals');
    if (elMetals) elMetals.textContent = `${metalsTimeStr} ET`;

    // Client-side session fallback if authoritative summary not yet loaded
    if (!state.hasAuthoritativeMarketSummary) {
      const pill = document.getElementById('radarPillMetals');
      const text = document.getElementById('radarStatusTextMetals');
      const card = document.getElementById('radarCardMetals');
      const detail = document.getElementById('radarDetailMetals');

      const usDate = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
      const day = usDate.getDay(); // 0=Sun, 5=Fri, 6=Sat
      const hrs = usDate.getHours();
      const mins = usDate.getMinutes();
      const totalM = hrs * 60 + mins;

      let isOpen = false;
      let statusDesc = '';

      if (day === 6) {
        isOpen = false;
        statusDesc = 'Metals market is CLOSED on Saturdays. Opens Sunday 18:00 ET.';
      } else if (day === 0) {
        if (totalM < 18 * 60) {
          isOpen = false;
          statusDesc = 'Metals market is CLOSED until Sunday 18:00 ET.';
        } else {
          isOpen = true;
          statusDesc = 'Metals market is OPEN (Sunday evening session).';
        }
      } else if (day === 5) {
        if (totalM >= 17 * 60) {
          isOpen = false;
          statusDesc = 'Metals market CLOSED for weekend at 17:00 ET.';
        } else {
          isOpen = true;
          statusDesc = 'Metals market is OPEN (Friday session). Closes 17:00 ET.';
        }
      } else {
        if (totalM >= 17 * 60 && totalM < 18 * 60) {
          isOpen = false;
          statusDesc = 'Metals maintenance pause (17:00-18:00 ET). Reopens at 18:00 ET.';
        } else {
          isOpen = true;
          statusDesc = 'Metals market is OPEN (CME/Globex Gold & Silver 23h session).';
        }
      }

      if (pill) pill.className = `radar-status-pill ${isOpen ? 'open' : 'closed'}`;
      if (text) text.textContent = isOpen ? 'OPEN' : 'CLOSED';
      if (card) {
        if (isOpen) card.classList.add('session-open');
        else card.classList.remove('session-open');
      }
      if (detail && statusDesc) detail.textContent = statusDesc;
    }
  } catch (e) {}
}

async function fetchMarketSummaryData() {
  try {
    const res = await fetch('/api/market-summary');
    if (!res.ok) return;
    const data = await res.json();
    state.hasAuthoritativeMarketSummary = true;

    // US Market Update
    const us = data.us_market;
    if (us) {
      const pill = document.getElementById('radarPillUS');
      const text = document.getElementById('radarStatusTextUS');
      const detail = document.getElementById('radarDetailUS');
      const card = document.getElementById('radarCardUS');

      if (us.open) {
        if (pill) pill.className = 'radar-status-pill open';
        if (text) text.textContent = 'OPEN';
        if (card) card.classList.add('session-open');
      } else {
        const isPre = us.status && us.status.includes('PRE-MARKET');
        if (pill) pill.className = `radar-status-pill ${isPre ? 'pre' : 'closed'}`;
        if (text) text.textContent = isPre ? 'PRE-MARKET' : 'CLOSED';
        if (card) card.classList.remove('session-open');
      }
      if (detail && us.status) {
        detail.textContent = us.status;
      }
    }

    // Indian Market Update
    const ind = data.indian_market;
    if (ind) {
      const pill = document.getElementById('radarPillIN');
      const text = document.getElementById('radarStatusTextIN');
      const detail = document.getElementById('radarDetailIN');
      const card = document.getElementById('radarCardIN');

      if (ind.open) {
        if (pill) pill.className = 'radar-status-pill open';
        if (text) text.textContent = 'OPEN';
        if (card) card.classList.add('session-open');
      } else {
        const isPre = ind.status && ind.status.includes('PRE-MARKET');
        if (pill) pill.className = `radar-status-pill ${isPre ? 'pre' : 'closed'}`;
        if (text) text.textContent = isPre ? 'PRE-MARKET' : 'CLOSED';
        if (card) card.classList.remove('session-open');
      }
      if (detail && ind.status) {
        detail.textContent = ind.status;
      }
    }

    // Metals Market Update
    const metals = data.metals_market;
    if (metals) {
      const pill = document.getElementById('radarPillMetals');
      const text = document.getElementById('radarStatusTextMetals');
      const detail = document.getElementById('radarDetailMetals');
      const card = document.getElementById('radarCardMetals');

      if (metals.open) {
        if (pill) pill.className = 'radar-status-pill open';
        if (text) text.textContent = 'OPEN';
        if (card) card.classList.add('session-open');
      } else {
        if (pill) pill.className = 'radar-status-pill closed';
        if (text) text.textContent = 'CLOSED';
        if (card) card.classList.remove('session-open');
      }
      if (detail && metals.status) {
        detail.textContent = metals.status;
      }
    }
  } catch (err) {
    console.debug('Failed to fetch market summary:', err);
  }
}

async function fetchScannerLogs() {
  try {
    const res = await fetch('/api/scanner-logs?limit=100');
    if (!res.ok) return;
    const data = await res.json();
    const logs = data.logs || [];

    if (logs.length === liveTradeState.lastLogCount) return;
    liveTradeState.lastLogCount = logs.length;

    const terminal = document.getElementById('liveTerminalOutput');
    if (!terminal) return;

    terminal.innerHTML = logs.map(log => {
      let cls = '';
      const lvl = (log.level || '').toUpperCase();
      if (lvl === 'CYCLE') cls = 'cycle';
      else if (lvl === 'FILLED') cls = 'filled';
      else if (lvl === 'BLOCKED') cls = 'blocked';
      else if (lvl === 'SIGNAL') cls = 'signal';
      else if (lvl === 'AI') cls = 'ai';

      return `<div class="terminal-line ${cls}"><span class="term-time">[${log.time}]</span> ${escapeHtml(log.message)}</div>`;
    }).join('');

    if (liveTradeState.autoScroll) {
      terminal.scrollTop = terminal.scrollHeight;
    }
  } catch (err) {
    console.error('Failed to fetch scanner logs:', err);
  }
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

async function updateLiveMetrics() {
  try {
    const res = await fetch('/api/account');
    if (!res.ok) return;
    const acc = await res.json();

    const el = (id, val) => {
      const node = document.getElementById(id);
      if (node) node.textContent = val;
    };

    el('livePortfolioVal', formatCurrency(acc.portfolio_value));
    el('liveCashVal', formatCurrency(acc.cash));

    const posRes = await fetch('/api/positions');
    if (!posRes.ok) return;
    const posData = await posRes.json();
    const positions = posData.positions || [];

    let totalUnrealizedPnl = 0;
    positions.forEach(p => { totalUnrealizedPnl += (p.unrealized_pnl || 0); });

    const pnlPct = acc.portfolio_value > 0 ? (totalUnrealizedPnl / acc.portfolio_value) : 0;
    const pnlEl = document.getElementById('liveUnrealizedPnl');
    if (pnlEl) {
      const sign = totalUnrealizedPnl >= 0 ? '+' : '';
      pnlEl.textContent = `${formatCurrency(totalUnrealizedPnl)} (${sign}${(pnlPct * 100).toFixed(2)}%)`;
      pnlEl.style.color = totalUnrealizedPnl >= 0 ? '#26A69A' : '#EF5350';
    }

    let realizedPnl = 0;
    try {
      const tradesRes = await fetch('/api/trades');
      if (tradesRes.ok) {
        const tradesData = await tradesRes.json();
        state.trades = tradesData.trades || [];
      }
    } catch (e) {
      // fallback to state.trades in memory
    }
    if (state.trades && state.trades.length > 0) {
      state.trades.forEach(t => { realizedPnl += (t.pnl || 0); });
    }
    const realizedEl = document.getElementById('liveRealizedPnl');
    if (realizedEl) {
      realizedEl.textContent = formatCurrency(realizedPnl);
      realizedEl.style.color = realizedPnl >= 0 ? '#26A69A' : '#EF5350';
    }

    el('livePositionsCount', `${positions.length} Active`);
  } catch (err) {
    console.error('Failed to update live metrics:', err);
  }
}

async function updateLivePositions() {
  try {
    const posRes = await fetch('/api/positions');
    if (!posRes.ok) return;
    const posData = await posRes.json();
    const positions = posData.positions || [];

    const tbody = document.getElementById('livePositionsTableBody');
    const badge = document.getElementById('livePositionsBadge');
    if (badge) badge.textContent = `${positions.length} Open`;

    if (!tbody) return;

    if (positions.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted py-6">No active positions yet. Scanner is searching for setups.</td></tr>';
    } else {
      tbody.innerHTML = positions.map(p => {
        const pnl = p.unrealized_pnl || 0;
        const pnlClass = pnl >= 0 ? 'text-bullish' : 'text-bearish';
        const isShort = (p.side || '').toUpperCase() === 'SHORT';
        const sideTagClass = isShort ? 'SELL' : 'BUY';
        const sideText = isShort ? 'SHORT' : 'LONG';
        return `
          <tr>
            <td><strong>${p.symbol}</strong></td>
            <td><span class="trade-action-tag ${sideTagClass}">${sideText}</span></td>
            <td><span class="timestamp-chip">${formatTime(p.opened_at)}</span></td>
            <td>${renderTargetExit(p)}</td>
            <td class="text-right mono">${Math.abs(p.quantity)}</td>
            <td class="text-right mono">${formatCurrency(p.entry_price)}</td>
            <td class="text-right mono">${formatCurrency(p.current_price)}</td>
            <td class="text-right mono ${pnlClass}">${formatCurrency(pnl)}</td>
            <td class="text-center">
              <button class="btn-close-pos" onclick="exitPosition('${p.symbol}')">CLOSE</button>
            </td>
          </tr>
        `;
      }).join('');
    }

    const tradesRes = await fetch('/api/trades');
    if (!tradesRes.ok) return;
    const tradesData = await tradesRes.json();
    const trades = tradesData.trades || [];
    state.trades = trades;

    const fillsStream = document.getElementById('liveFillsStream');
    const fillsBadge = document.getElementById('liveFillsBadge');
    if (fillsBadge) fillsBadge.textContent = `${trades.length} Fills`;

    if (!fillsStream) return;

    if (trades.length === 0) {
      fillsStream.innerHTML = '<div class="empty-state-text">No orders filled yet today.</div>';
    } else {
      fillsStream.innerHTML = trades.slice(-15).reverse().map(t => {
        const isBuy = (t.side || t.action) === 'BUY';
        const tagClass = isBuy ? 'BUY' : 'SELL';
        const sideText = isBuy ? 'LONG' : 'SHORT';
        const pnl = t.pnl || 0;
        const pnlText = pnl !== 0 ? `<span class="mono ${pnl > 0 ? 'text-bullish' : 'text-bearish'}">${formatCurrency(pnl)}</span>` : '<span class="text-muted">$0.00</span>';
        const reasonClass = t.reason || 'SIGNAL_EXIT';
        const reasonLabel = (t.reason || 'EXIT').replace('_', ' ');
        const exitPrice = t.exit_price || t.entry_price || t.price || 0;
        return `
          <div class="trade-item">
            <div class="trade-item-left">
              <span class="trade-action-tag ${tagClass}">${sideText}</span>
              <strong>${t.symbol}</strong>
              <span class="text-muted">${t.quantity} @ ${formatCurrency(exitPrice)}</span>
              <span class="trade-reason-chip ${reasonClass}">${reasonLabel}</span>
            </div>
            <div class="trade-item-right mono text-right">
              <div>${pnlText}</div>
              <div class="timestamp-chip" title="Opened ➔ Closed">${formatTime(t.entry_time)} ➔ ${formatTime(t.exit_time)}</div>
            </div>
          </div>
        `;
      }).join('');
    }
  } catch (err) {
    console.error('Failed to update live positions:', err);
  }
}

function refreshLiveTradeView() {
  fetchScannerLogs();
  updateLiveMetrics();
  updateLivePositions();
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
  fetchMarketSummaryData();
  fetchAgentSwarmData();
  updateTimezoneRadarClocks();
  if (liveTradeState.activeTab === 'tabLiveTrade') {
    refreshLiveTradeView();
  }
}

window.addEventListener('DOMContentLoaded', () => {
  chartRenderer = new FinancialChartRenderer('financialChartCanvas');

  // Start real-time ticking timezone radar clocks (every 1 second)
  updateTimezoneRadarClocks();
  setInterval(updateTimezoneRadarClocks, 1000);

  // Symbol Selector
  const symbolSelect = document.getElementById('symbolSelect');
  symbolSelect.addEventListener('change', (e) => {
    state.activeSymbol = e.target.value;
    document.getElementById('orderSymbol').value = state.activeSymbol;
    const barCountEl = document.getElementById('chartBarCount');
    if (barCountEl) barCountEl.textContent = `Loading ${state.activeSymbol}...`;
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

  // Tab Navigation Bindings
  document.getElementById('btnTabOverview').addEventListener('click', () => switchTab('tabOverview'));
  document.getElementById('btnTabLiveTrade').addEventListener('click', () => switchTab('tabLiveTrade'));
  const btnSwarm = document.getElementById('btnTabAgentSwarm');
  if (btnSwarm) btnSwarm.addEventListener('click', () => switchTab('tabAgentSwarm'));

  // Terminal Controls
  const btnAutoScroll = document.getElementById('btnAutoScroll');
  if (btnAutoScroll) {
    btnAutoScroll.addEventListener('click', () => {
      liveTradeState.autoScroll = !liveTradeState.autoScroll;
      btnAutoScroll.textContent = `AUTO-SCROLL: ${liveTradeState.autoScroll ? 'ON' : 'OFF'}`;
      btnAutoScroll.style.color = liveTradeState.autoScroll ? '#26A69A' : '#EF5350';
    });
  }

  const btnClearTerminal = document.getElementById('btnClearTerminal');
  if (btnClearTerminal) {
    btnClearTerminal.addEventListener('click', () => {
      const terminal = document.getElementById('liveTerminalOutput');
      if (terminal) terminal.innerHTML = '<div class="terminal-line text-muted">[System] Terminal cleared by user.</div>';
      liveTradeState.lastLogCount = 0;
    });
  }

  // Background Poll every 3 seconds
  state.pollInterval = setInterval(() => {
    refreshAll();
    if (liveTradeState.activeTab === 'tabLiveTrade') {
      refreshLiveTradeView();
    }
  }, 3000);

  // Dedicated high-frequency 1-second poll for Agent Swarm HUD (smooth progress bar & real-time telemetry)
  setInterval(() => {
    if (liveTradeState.activeTab === 'tabAgentSwarm') {
      fetchAgentSwarmData();
    }
  }, 1000);
});
