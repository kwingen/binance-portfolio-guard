<template>
  <div class="card" style="margin-top:12px">
    <!-- 全局止损线 -->
    <div class="global-sl">
      <div class="global-sl-row">
        <span class="global-sl-label">全局止损</span>
        <span class="global-sl-value">{{ store.effectiveThresholdFormatted }} USDT</span>
        <span v-if="store.thresholdType === 'percent'" class="global-sl-meta">(开仓成本 × {{ store.threshold }}%)</span>
        <span class="global-sl-mode" :style="{color: store.monitoring ? 'var(--green)' : 'var(--text-dim)'}">
          {{ store.monitoring ? '🟢 监控中' : '⏸ 已停止' }}
        </span>
      </div>
    </div>

    <div class="card-header">
      <h3>持仓 ({{ totalCount }})</h3>
      <div class="header-actions">
        <button v-if="!editing" class="btn btn-blue" @click="editing = true">📦 管理分组</button>
        <button v-else class="btn btn-green" @click="saveGroups">💾 保存分组</button>
        <button v-if="editing" class="btn btn-ghost" @click="cancelEdit">取消</button>
      </div>
    </div>

    <!-- 编辑模式 -->
    <div v-if="editing" class="group-editor">
      <!-- 可用仓位 -->
      <div style="margin-bottom:10px">
        <label style="font-size:12px;color:var(--text-dim);font-weight:600">我的持仓（点击加入分组）</label>
        <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px">
          <span v-for="(p, pi) in availablePositions" :key="pi"
            class="pos-pick"
            :class="{ picked: pickedPositions[positionKey(p)] }"
            @click="togglePick(p)">
            <strong>{{ p.symbol }}</strong> {{ parseFloat(p.positionAmt) > 0 ? '📈多' : '📉空' }}
            <span class="pick-pnl" :class="parseFloat(p.unRealizedProfit) >= 0 ? 'green' : 'red'">{{ fmtPnl(p.unRealizedProfit) }}</span>
          </span>
          <span v-if="!availablePositions.length" style="font-size:12px;color:var(--text-dim)">无可用仓位</span>
        </div>
      </div>
      <div v-for="(g, gi) in editGroups" :key="gi" class="edit-group">
        <div class="edit-row">
          <input v-model="g.name" placeholder="组名" class="med-input" style="width:100px">
          <input v-model.number="g.stop_loss_threshold" type="number" step="0.1" class="med-input" style="width:65px">
          <select v-model="g.threshold_type" class="med-select">
            <option value="percent">%</option>
            <option value="usd">USDT</option>
          </select>
          <button class="btn btn-sm btn-blue" @click="addPickedToGroup(gi)">+ 已选仓位</button>
          <button class="btn btn-sm btn-red" @click="editGroups.splice(gi,1)">✕</button>
        </div>
        <div class="edit-positions">
          <span v-for="(p, pi) in g.positions" :key="pi" class="pos-tag">
            {{ p.symbol }} {{ p.direction === 'long' ? '多' : '空' }}
            <button @click="g.positions.splice(pi,1); unpickPos(p)" class="tag-remove">×</button>
          </span>
          <span v-if="!g.positions.length" style="font-size:12px;color:var(--text-dim)">点击上方仓位加入</span>
        </div>
      </div>
      <button class="btn btn-blue" @click="addGroup">+ 添加分组</button>
    </div>

    <!-- 分组视图 -->
    <div v-if="store.groups.length && !editing">
      <div v-for="(g, i) in store.groups" :key="i" class="group-block">
        <div class="group-header">
          <span class="group-name">📦 {{ g.name }}</span>
          <span :class="g.pnl >= 0 ? 'green' : 'red'">{{ g.pnl_formatted }}</span>
          <span class="group-threshold">
            止损
            <template v-if="g.threshold_type === 'percent'">{{ g.threshold_pct }}% = </template>
            {{ g.threshold_formatted }} USDT
          </span>
        </div>
        <PositionTable :positions="g.positions" />
      </div>
    </div>

    <!-- 未分组 -->
    <div v-if="ungroupedPositions.length" class="group-block">
      <div class="group-header">
        <span class="group-name">📋 未分组</span>
        <span :class="ungroupedPnl >= 0 ? 'green' : 'red'">{{ ungroupedPnlFormatted }}</span>
        <span class="group-threshold">全局止损 {{ store.effectiveThresholdFormatted }} USDT</span>
      </div>
      <PositionTable :positions="ungroupedPositions" />
    </div>

    <!-- 无仓位 -->
    <div v-if="!store.positions.length && !editing" class="empty-state">暂无持仓</div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { api } from '../api/client.js'
import { useTradingStore } from '../stores/trading.js'
import PositionTable from './PositionTable.vue'

const store = useTradingStore()
const editing = ref(false)
const editGroups = ref([])
const pickedPositions = ref({})

const totalCount = computed(() => store.positions.length)

const ungroupedPositions = computed(() => {
  if (!store.groups.length) return store.positions
  const groupedSyms = new Set()
  store.groups.forEach(g => g.positions.forEach(p => {
    groupedSyms.add(p.symbol + (parseFloat(p.positionAmt) > 0 ? '_long' : '_short'))
  }))
  return store.positions.filter(p => {
    const key = p.symbol + (parseFloat(p.positionAmt) > 0 ? '_long' : '_short')
    return !groupedSyms.has(key)
  })
})

const ungroupedPnl = computed(() => ungroupedPositions.value.reduce((sum, p) => sum + parseFloat(p.unRealizedProfit || 0), 0))
const ungroupedPnlFormatted = computed(() => (ungroupedPnl.value >= 0 ? '+' : '') + ungroupedPnl.value.toFixed(2))

watch(editing, async (val) => {
  if (val) {
    const s = await api.getSettings()
    editGroups.value = JSON.parse(JSON.stringify(s.portfolios || []))
    newSym.value = {}
    newDir.value = {}
  }
})

const availablePositions = computed(() => {
  // 不在任何编辑中分组里的仓位
  const used = new Set()
  editGroups.value.forEach(g => g.positions.forEach(p => {
    used.add(p.symbol + '_' + p.direction)
  }))
  return store.positions.filter(p => {
    const dir = parseFloat(p.positionAmt) > 0 ? 'long' : 'short'
    return !used.has(p.symbol + '_' + dir)
  })
})

function positionKey(pos) {
  return pos.symbol + '_' + (parseFloat(pos.positionAmt) > 0 ? 'long' : 'short')
}
function fmtPnl(v) { const n = parseFloat(v); return isNaN(n) ? '0.00' : (n >= 0 ? '+' : '') + n.toFixed(2) }
function togglePick(p) {
  const k = positionKey(p)
  pickedPositions.value = { ...pickedPositions.value, [k]: !pickedPositions.value[k] }
}
function unpickPos(p) {
  const k = positionKey(p)
  const newPicks = { ...pickedPositions.value }
  delete newPicks[k]
  pickedPositions.value = newPicks
}
function addPickedToGroup(gi) {
  const dir = (pos) => parseFloat(pos.positionAmt) > 0 ? 'long' : 'short'
  store.positions.filter(p => pickedPositions.value[positionKey(p)]).forEach(p => {
    if (!editGroups.value[gi].positions.find(ep => ep.symbol === p.symbol && ep.direction === dir(p))) {
      editGroups.value[gi].positions.push({ symbol: p.symbol, direction: dir(p) })
    }
  })
  pickedPositions.value = {}
}

function addGroup() {
  editGroups.value.push({ name: 'Group ' + (editGroups.value.length + 1), positions: [], stop_loss_threshold: 5, threshold_type: 'percent', enabled: true })
}

async function saveGroups() {
  await api.saveSettings({ portfolios: editGroups.value })
  await store.fetchStatus()
  await store.fetchSettings()
  editing.value = false
}
function cancelEdit() { editing.value = false }
</script>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.card-header h3 { margin-bottom: 0; font-size: 13px; color: var(--text-dim); text-transform: uppercase; }
.header-actions { display: flex; gap: 4px; }
.group-editor { border: 1px solid var(--border); border-radius: 8px; padding: 10px; margin-bottom: 10px; background: var(--bg); }
.edit-group { border: 1px solid var(--border); border-radius: 6px; padding: 8px; margin-bottom: 6px; }
.edit-row { display: flex; gap: 4px; align-items: center; margin-bottom: 4px; }
.edit-positions { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.med-input, .med-select {
  background: var(--bg); border: 1px solid var(--border); color: var(--text);
  padding: 5px 8px; border-radius: 5px; font-size: 12px;
}
.pos-tag {
  font-size: 12px; background: var(--card-bg); padding: 4px 8px; border-radius: 5px;
  display: inline-flex; align-items: center; gap: 3px;
}
.tag-remove { cursor: pointer; border: none; background: none; color: var(--red); font-size: 14px; }
.btn-sm { padding: 6px 12px; border: none; border-radius: 5px; font-size: 12px; cursor: pointer; }
.btn { padding: 8px 16px; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; }
.group-block { margin-bottom: 8px; }
.group-header {
  display: flex; align-items: center; gap: 10px; padding: 6px 0;
  border-bottom: 1px solid var(--border); margin-bottom: 4px;
}
.group-name { font-size: 13px; font-weight: 600; }
.group-threshold { font-size: 11px; color: var(--text-dim); margin-left: auto; }
.green { color: var(--green); }
.red { color: var(--red); }
.empty-state { text-align: center; padding: 32px; color: var(--text-dim); }
.global-sl {
  background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
  padding: 8px 12px; margin-bottom: 10px;
}
.global-sl-row { display: flex; align-items: center; gap: 10px; }
.global-sl-label { font-size: 12px; color: var(--text-dim); font-weight: 600; }
.global-sl-value { font-size: 14px; font-weight: 700; color: var(--red); }
.global-sl-meta { font-size: 11px; color: var(--text-dim); }
.global-sl-mode { font-size: 12px; margin-left: auto; }
.btn { padding: 8px 16px; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; }
.btn-blue { background: var(--blue); color: #fff; }
.btn-green { background: var(--green); color: #000; }
.btn-ghost { background: transparent; border: 1px solid var(--border); color: var(--text); }
.btn-red { background: var(--red); color: #fff; }
.btn-xs { padding: 4px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; }
.header-actions { display: flex; gap: 8px; }
.pos-pick {
  font-size: 13px; padding: 6px 10px; border-radius: 6px; cursor: pointer;
  border: 1px solid var(--border); background: var(--card-bg);
  display: inline-flex; align-items: center; gap: 6px; user-select: none;
}
.pos-pick:hover { border-color: var(--blue); }
.pos-pick.picked { background: rgba(68,138,255,0.15); border-color: var(--blue); }
.pick-pnl { font-size: 12px; font-weight: 600; }
</style>
