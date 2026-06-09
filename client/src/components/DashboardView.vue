<template>
  <div class="dashboard">
    <!-- 顶部栏 -->
    <header class="topbar">
      <div class="topbar-left">
        <h1>📊 Binance 总仓位止损</h1>
        <span class="badge" :class="modeBadgeClass">{{ modeBadge }}</span>
        <span v-if="!store.hasApiKey" class="badge badge-red">⚠ 未配置API</span>
      </div>
      <div class="topbar-right">
        <label class="sl-label">止损:</label>
        <input v-model.number="thresholdInput" type="number" step="0.1" class="sl-input">
        <select v-model="thresholdTypeInput" class="sl-select">
          <option value="usd">USDT</option>
          <option value="percent">%</option>
        </select>
        <button class="btn btn-blue" @click="applyThreshold">应用</button>
        <button class="btn btn-green" @click="startMonitor">▶ 启动</button>
        <button class="btn btn-ghost" @click="stopMonitor">⏸ 停止</button>
        <button class="btn btn-ghost" @click="showSettings = true">⚙️</button>
        <button class="btn btn-ghost" @click="logout">退出</button>
      </div>
    </header>

    <!-- 卡片区 -->
    <div class="grid">
      <div class="card">
        <h3>总未实现盈亏</h3>
        <div class="pnl-big" :class="pnlClass">{{ store.totalPnlFormatted }}</div>
        <div class="pnl-meta">
          开仓成本: {{ store.totalEntryValue.toFixed(2) }} USDT ｜ 市值: {{ store.totalNotional.toFixed(2) }} USDT
        </div>
      </div>
      <div class="card">
        <h3>账户概览</h3>
        <div class="metric-row"><span>钱包余额</span><span>{{ store.account.totalWalletBalance || '—' }}</span></div>
        <div class="metric-row"><span>保证金余额</span><span>{{ store.account.totalMarginBalance || '—' }}</span></div>
        <div class="metric-row"><span>可用余额</span><span>{{ store.account.availableBalance || '—' }}</span></div>
        <div class="metric-row"><span>最近检查</span><span>{{ store.lastCheckTime || '—' }}</span></div>
      </div>
      <div class="card">
        <h3>监控状态</h3>
        <div class="metric-row"><span>状态</span><span :style="monitorStateStyle">{{ monitorStateText }}</span></div>
        <div class="metric-row"><span>检查次数</span><span>{{ store.totalChecks }}</span></div>
        <div class="metric-row"><span>止损线</span><span>{{ store.effectiveThresholdFormatted }} USDT <template v-if="store.thresholdType==='percent'">(开仓成本×{{ store.threshold }}%)</template></span></div>
        <div class="metric-row"><span>模式</span><span>{{ store.dryRun ? '🏗 演习' : '⚡ 实盘' }}</span></div>
      </div>
    </div>

    <!-- 持仓（按分组） -->
    <PortfolioGroupView />

    <!-- 紧急清仓 -->
    <EmergencyButton />

    <!-- 日志 -->
    <div class="card" style="margin-top:12px">
      <h3>实时日志</h3>
      <LogStream :logs="store.logs" />
    </div>

    <!-- 设置面板 -->
    <SettingsModal v-if="showSettings" @close="showSettings = false" @saved="onSettingsSaved" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { useTradingStore } from '../stores/trading.js'
import { api } from '../api/client.js'
import PortfolioGroupView from './PortfolioGroupView.vue'
import EmergencyButton from './EmergencyButton.vue'
import LogStream from './LogStream.vue'
import SettingsModal from './SettingsModal.vue'

const router = useRouter()
const auth = useAuthStore()
const store = useTradingStore()

const showSettings = ref(false)
const thresholdInput = ref(5)
const thresholdTypeInput = ref('percent')

let sseSource = null
let pollTimer = null

// 计算属性
const modeBadge = computed(() => store.testnet ? '测试网' : store.dryRun ? 'DEMO' : 'LIVE')
const modeBadgeClass = computed(() => store.testnet ? 'badge-demo' : store.dryRun ? 'badge-demo' : 'badge-live')
const pnlClass = computed(() => store.totalPnl >= 0 ? 'positive' : 'negative')
const monitorStateText = computed(() => {
  if (store.stopLossTriggered) return '🚨 已触发止损'
  if (store.monitoring) return '🟢 监控中'
  return '⏸ 已停止'
})
const monitorStateStyle = computed(() => ({
  color: store.stopLossTriggered ? 'var(--red)' : store.monitoring ? 'var(--green)' : 'var(--text-dim)'
}))

// SSE
function connectSSE() {
  if (sseSource) sseSource.close()
  sseSource = new EventSource('/api/events')
  sseSource.addEventListener('connected', () => store.fetchStatus())
  sseSource.addEventListener('position_update', (e) => {
    const d = JSON.parse(e.data)
    store.positions = d.positions || []
    store.totalPnl = d.total_pnl
    store.totalPnlFormatted = d.total_pnl_formatted
    store.totalNotional = d.total_notional
    store.totalEntryValue = d.total_entry_value
    store.lastCheckTime = d.time
    store.groups = d.groups || []
    store.effectiveThresholdFormatted = d.effective_threshold_formatted || store.effectiveThresholdFormatted
  })
  sseSource.addEventListener('stop_loss_triggered', () => {
    store.stopLossTriggered = true
    store.monitoring = false
    store.addLog('error', '🚨 止损触发!')
    store.fetchStatus()
  })
  sseSource.addEventListener('emergency_close', (e) => {
    const d = JSON.parse(e.data)
    store.addLog('warn', `🔥 紧急清仓: 成功 ${d.success}`)
    store.fetchStatus()
  })
  sseSource.addEventListener('config_updated', () => store.fetchStatus())
  sseSource.addEventListener('monitor_status', (e) => {
    store.monitoring = JSON.parse(e.data).monitoring
  })
  sseSource.addEventListener('error', (e) => {
    try { store.addLog('error', JSON.parse(e.data).message) } catch(_) {}
  })
  sseSource.onerror = () => {
    store.addLog('error', 'SSE 断开，5秒后重连...')
    setTimeout(connectSSE, 5000)
  }
}

async function applyThreshold() {
  try {
    await api.applyConfig({ stop_loss_threshold: thresholdInput.value, threshold_type: thresholdTypeInput.value })
    store.addLog('info', `止损: ${thresholdInput.value} ${thresholdTypeInput.value === 'percent' ? '%' : 'USDT'}`)
  } catch(e) { store.addLog('error', e.message) }
}

async function startMonitor() {
  try { await api.startMonitor(); store.addLog('info', '监控已启动') } catch(e) { store.addLog('error', e.message) }
}
async function stopMonitor() {
  try { await api.stopMonitor(); store.addLog('info', '监控已停止') } catch(e) { store.addLog('error', e.message) }
}

function onSettingsSaved() {
  store.fetchStatus()
  store.fetchSettings()
}

function logout() {
  auth.logout()
  router.push('/login')
}

onMounted(async () => {
  await Promise.all([store.fetchStatus(), store.fetchSettings()])
  thresholdInput.value = store.threshold
  thresholdTypeInput.value = store.thresholdType
  connectSSE()
  pollTimer = setInterval(() => store.fetchStatus(), 30000)

  // 当 store 被 SSE 更新时同步顶部输入框
  watch(() => store.threshold, v => { thresholdInput.value = v })
  watch(() => store.thresholdType, v => { thresholdTypeInput.value = v })
})
onUnmounted(() => {
  if (sseSource) sseSource.close()
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.dashboard { padding: 16px; }
.topbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; flex-wrap: wrap; gap: 8px; }
.topbar-left { display: flex; align-items: center; gap: 10px; }
.topbar-left h1 { font-size: 20px; font-weight: 600; }
.topbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.sl-label { color: var(--text-dim); font-size: 12px; }
.sl-input { width: 75px; background: var(--bg); border: 1px solid var(--border); color: var(--text); padding: 6px 8px; border-radius: 6px; font-size: 13px; }
.sl-select { background: var(--bg); border: 1px solid var(--border); color: var(--text); padding: 6px 8px; border-radius: 6px; font-size: 13px; }
.grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
.card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; padding: 16px; }
.card h3 { font-size: 13px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
.pnl-big { font-size: 42px; font-weight: 700; line-height: 1.1; }
.pnl-big.positive { color: var(--green); }
.pnl-big.negative { color: var(--red); }
.pnl-meta { margin-top: 4px; font-size: 12px; color: var(--text-dim); }
.metric-row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 14px; border-bottom: 1px solid rgba(255,255,255,0.04); }
.metric-row:last-child { border-bottom: none; }
.metric-row span:first-child { color: var(--text-dim); }
.btn { padding: 8px 16px; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-green { background: var(--green); color: #000; }
.btn-blue { background: var(--blue); color: #fff; }
.btn-ghost { background: transparent; border: 1px solid var(--border); color: var(--text); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
.badge-live { background: rgba(0,200,83,0.15); color: var(--green); }
.badge-demo { background: rgba(255,145,0,0.15); color: var(--orange); }
.badge-red { background: rgba(255,23,68,0.15); color: var(--red); }
</style>
