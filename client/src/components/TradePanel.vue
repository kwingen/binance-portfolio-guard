<template>
  <div class="trade-panel">
    <!-- 顶部：交易对选择 -->
    <div class="trade-header">
      <input v-model="symbol" class="symbol-input" placeholder="BTCUSDT" @change="switchSymbol">
      <span v-if="ticker" class="ticker-info">
        <span :class="ticker.priceChange >= 0 ? 'green' : 'red'">{{ fmtPrice(ticker.lastPrice) }}</span>
        <span class="change" :class="ticker.priceChange >= 0 ? 'green' : 'red'">{{ ticker.priceChange >= 0 ? '+' : '' }}{{ ticker.priceChangePercent.toFixed(2) }}%</span>
      </span>
      <div class="interval-btns">
        <button v-for="i in intervals" :key="i" :class="['btn-xs', interval === i ? 'btn-blue' : 'btn-ghost']" @click="interval = i; fetchKlines()">{{ i }}</button>
      </div>
    </div>

    <div class="trade-body">
      <!-- 左侧：K线图 -->
      <div class="chart-section">
        <div ref="chartEl" class="chart-container"></div>
      </div>

      <!-- 右侧：订单簿 + 下单 -->
      <div class="side-section">
        <!-- 订单簿 -->
        <div class="orderbook">
          <h4>订单簿</h4>
          <div class="depth-rows">
            <div v-for="(lvl, i) in asks.slice(0, 10)" :key="'a'+i" class="depth-row ask">
              <span class="price red">{{ fmtPrice(lvl.price) }}</span>
              <span class="qty">{{ fmtQty(lvl.qty) }}</span>
              <span class="cum" :style="{width: (lvl.cum / maxDepth * 100) + '%'}"></span>
            </div>
            <div class="spread-row">
              <span class="spread">价差: {{ spread.toFixed(1) }} ({{ spreadPct.toFixed(3) }}%)</span>
            </div>
            <div v-for="(lvl, i) in bids.slice(0, 10)" :key="'b'+i" class="depth-row bid">
              <span class="price green">{{ fmtPrice(lvl.price) }}</span>
              <span class="qty">{{ fmtQty(lvl.qty) }}</span>
              <span class="cum" :style="{width: (lvl.cum / maxDepth * 100) + '%'}"></span>
            </div>
          </div>
        </div>

        <!-- 下单 -->
        <div class="trade-form">
          <h4>下单</h4>
          <div class="btn-group">
            <button :class="['btn-sm', side === 'BUY' ? 'btn-green' : 'btn-ghost']" @click="side = 'BUY'">📈 做多</button>
            <button :class="['btn-sm', side === 'SELL' ? 'btn-red' : 'btn-ghost']" @click="side = 'SELL'">📉 做空</button>
          </div>
          <div class="btn-group" style="margin-top:4px">
            <button :class="['btn-xs', orderType === 'MARKET' ? 'btn-blue' : 'btn-ghost']" @click="orderType = 'MARKET'">市价</button>
            <button :class="['btn-xs', orderType === 'LIMIT' ? 'btn-blue' : 'btn-ghost']" @click="orderType = 'LIMIT'">限价</button>
          </div>
          <input v-if="orderType === 'LIMIT'" v-model.number="price" type="number" step="0.01" placeholder="限价" class="form-input">
          <div style="display:flex;gap:6px;margin-top:6px">
            <input v-model.number="quantity" type="number" step="0.001" placeholder="数量" class="form-input" style="flex:2">
            <input v-model.number="leverage" type="number" min="1" max="125" placeholder="杠杆" class="form-input" style="flex:1">
          </div>
          <button class="btn-submit" :class="side === 'BUY' ? 'btn-green' : 'btn-red'" @click="submit" :disabled="submitting">
            {{ submitting ? '...' : (side === 'BUY' ? '📈 做多 ' : '📉 做空 ') + symbol.toUpperCase() }}
          </button>
          <p v-if="status" class="status-msg" :class="statusType">{{ status }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick, computed } from 'vue'
import { useTradingStore } from '../stores/trading.js'

// lightweight-charts 动态导入避免模块初始化时序问题
let createChartFn = null, ColorType = null
async function loadChartLib() {
  if (!createChartFn) {
    const mod = await import('lightweight-charts')
    createChartFn = mod.createChart
    ColorType = mod.ColorType
  }
  return { createChart: createChartFn, ColorType }
}

const store = useTradingStore()

// ── 状态 ──
const symbol = ref('BTCUSDT')
const side = ref('BUY')
const orderType = ref('MARKET')
const quantity = ref(0.001)
const leverage = ref(10)
const price = ref(null)
const interval = ref('1m')
const intervals = ['1m', '5m', '15m', '1h', '4h', '1d']
const submitting = ref(false)
const status = ref('')
const statusType = ref('')

const ticker = ref(null)
const asks = ref([])
const bids = ref([])
const chartEl = ref(null)

let chart = null
let candleSeries = null
let ws = null
let wsDepth = null

// ── 计算 ──
const spread = computed(() => {
  if (!asks.value[0] || !bids.value[0]) return 0
  return asks.value[0].price - bids.value[0].price
})
const spreadPct = computed(() => {
  if (!asks.value[0] || !bids.value[0]) return 0
  return spread.value / asks.value[0].price * 100
})
const maxDepth = computed(() => {
  const allCum = [...asks.value, ...bids.value].map(l => l.cum || 0)
  return Math.max(...allCum, 1)
})

// ── 图表 ──
async function initChart() {
  if (!chartEl.value) return
  if (chart) { chart.remove(); chart = null }
  const { createChart: cc, ColorType: ct } = await loadChartLib()
  chart = cc(chartEl.value, {
    layout: { background: { type: ct.Solid, color: '#1a1d27' }, textColor: '#888' },
    grid: { vertLines: { color: '#2a2d37' }, horzLines: { color: '#2a2d37' } },
    width: chartEl.value.clientWidth,
    height: chartEl.value.clientHeight,
    timeScale: { timeVisible: true },
  })
  candleSeries = chart.addCandlestickSeries({
    upColor: '#00c853', downColor: '#ff1744', borderUpColor: '#00c853', borderDownColor: '#ff1744',
    wickUpColor: '#00c853', wickDownColor: '#ff1744',
  })
}

async function fetchKlines() {
  const sym = symbol.value.toUpperCase()
  const limit = interval.value === '1m' ? 200 : 100
  try {
    const res = await fetch(`https://fapi.binance.com/fapi/v1/klines?symbol=${sym}&interval=${interval.value}&limit=${limit}`)
    const data = await res.json()
    if (!candleSeries) return
    const ohlc = data.map(d => ({
      time: d[0] / 1000, open: +d[1], high: +d[2], low: +d[3], close: +d[4],
    }))
    candleSeries.setData(ohlc)
    chart?.timeScale().fitContent()
  } catch (_) {}
}

// ── WebSocket ──
function connectWS() {
  const sym = symbol.value.toLowerCase()
  if (ws) ws.close()
  // Ticker
  ws = new WebSocket(`wss://fstream.binance.com/ws/${sym}@ticker`)
  ws.onmessage = (e) => {
    const d = JSON.parse(e.data)
    ticker.value = {
      lastPrice: +d.c, priceChange: +d.p, priceChangePercent: +d.P,
      high: +d.h, low: +d.l, volume: +d.v,
    }
  }
  // Depth
  if (wsDepth) wsDepth.close()
  wsDepth = new WebSocket(`wss://fstream.binance.com/ws/${sym}@depth20@100ms`)
  wsDepth.onmessage = (e) => {
    const d = JSON.parse(e.data)
    let cumA = 0, cumB = 0
    asks.value = d.asks.slice(0, 10).map(a => {
      cumA += +a[1]; return { price: +a[0], qty: +a[1], cum: cumA }
    }).reverse()
    bids.value = d.bids.slice(0, 10).map(b => {
      cumB += +b[1]; return { price: +b[0], qty: +b[1], cum: cumB }
    })
  }
}

function switchSymbol() {
  fetchKlines()
  connectWS()
}

// ── 下单 ──
async function submit() {
  if (!symbol.value || quantity.value <= 0) return
  submitting.value = true; status.value = ''
  try {
    const res = await fetch('/api/order', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ symbol: symbol.value.toUpperCase(), side: side.value, order_type: orderType.value, quantity: quantity.value, price: orderType.value === 'LIMIT' ? price.value : undefined, leverage: leverage.value })
    })
    const data = await res.json()
    if (res.ok) {
      status.value = '✅ 下单成功' + (data.dry_run ? ' [DRY RUN]' : '')
      statusType.value = 'ok'
      store.addLog('info', `下单: ${side.value} ${quantity.value} ${symbol.value.toUpperCase()}`)
    } else {
      status.value = '❌ ' + (data.detail || '失败'); statusType.value = 'err'
    }
  } catch (e) {
    status.value = '❌ ' + e.message; statusType.value = 'err'
  }
  submitting.value = false
  setTimeout(() => { status.value = '' }, 5000)
}

// ── 工具 ──
function fmtPrice(v) { return v ? (+v).toFixed(v > 100 ? 2 : 4) : '—' }
function fmtQty(v) { return v ? (+v).toFixed(v > 100 ? 1 : 4) : '—' }

// ── 生命周期 ──
onMounted(async () => {
  await nextTick()
  initChart()
  fetchKlines()
  connectWS()
})
onUnmounted(() => {
  if (chart) chart.remove()
  if (ws) ws.close()
  if (wsDepth) wsDepth.close()
})
</script>

<style scoped>
.trade-panel { margin-top: 12px; display: flex; flex-direction: column; gap: 8px; }
.trade-header {
  display: flex; align-items: center; gap: 10px;
  background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; padding: 8px 12px;
}
.symbol-input {
  background: var(--bg); border: 1px solid var(--border); color: var(--text);
  padding: 6px 10px; border-radius: 6px; font-size: 14px; width: 100px; text-transform: uppercase; font-weight: 600;
}
.ticker-info { font-size: 14px; display: flex; gap: 8px; align-items: center; }
.change { font-size: 12px; }
.green { color: var(--green); }
.red { color: var(--red); }
.interval-btns { display: flex; gap: 2px; margin-left: auto; }

.trade-body { display: flex; gap: 8px; }
.chart-section { flex: 1; min-width: 0; background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; padding: 8px; }
.chart-container { width: 100%; height: 400px; }
.side-section { width: 320px; display: flex; flex-direction: column; gap: 8px; flex-shrink: 0; }

.orderbook { background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; padding: 10px; }
.orderbook h4 { font-size: 12px; color: var(--text-dim); margin-bottom: 6px; }
.depth-rows { font-size: 11px; }
.depth-row { display: flex; position: relative; padding: 2px 0; }
.depth-row .price { width: 70px; text-align: right; font-variant-numeric: tabular-nums; }
.depth-row .qty { width: 60px; text-align: right; font-variant-numeric: tabular-nums; color: var(--text-dim); }
.depth-row .cum { position: absolute; right: 0; top: 0; height: 100%; opacity: 0.08; }
.depth-row.ask .cum { background: var(--red); }
.depth-row.bid .cum { background: var(--green); }
.spread-row { text-align: center; padding: 4px 0; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); margin: 4px 0; }
.spread { font-size: 11px; color: var(--text-dim); }

.trade-form { background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; padding: 10px; }
.trade-form h4 { font-size: 12px; color: var(--text-dim); margin-bottom: 6px; }
.btn-group { display: flex; gap: 4px; }
.btn-sm {
  flex: 1; padding: 6px; border: 1px solid var(--border); border-radius: 6px;
  font-size: 12px; cursor: pointer; background: transparent; color: var(--text);
}
.btn-xs {
  flex: 1; padding: 4px; border: 1px solid var(--border); border-radius: 4px;
  font-size: 11px; cursor: pointer; background: transparent; color: var(--text);
}
.btn-green { background: var(--green) !important; color: #000 !important; border-color: var(--green) !important; }
.btn-red { background: var(--red) !important; color: #fff !important; border-color: var(--red) !important; }
.btn-blue { background: var(--blue) !important; color: #fff !important; border-color: var(--blue) !important; }
.btn-ghost { background: transparent; color: var(--text-dim); }
.form-input {
  width: 100%; background: var(--bg); border: 1px solid var(--border); color: var(--text);
  padding: 8px; border-radius: 6px; font-size: 12px; margin-top: 6px;
}
.btn-submit {
  width: 100%; padding: 10px; border: none; border-radius: 8px; font-size: 14px;
  font-weight: 600; cursor: pointer; margin-top: 8px;
}
.btn-submit:disabled { opacity: 0.5; cursor: not-allowed; }
.status-msg { font-size: 12px; margin-top: 6px; text-align: center; }
.status-msg.ok { color: var(--green); }
.status-msg.err { color: var(--red); }
</style>
