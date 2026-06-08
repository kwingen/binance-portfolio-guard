<template>
  <div v-if="!positions.length" class="empty-state">暂无持仓</div>
  <div v-else style="overflow-x:auto">
    <table>
      <thead><tr>
        <th>交易对</th><th>方向</th><th>数量</th><th>开仓价</th><th>标记价</th><th>杠杆</th><th>价值</th><th>盈亏</th>
      </tr></thead>
      <tbody>
        <tr v-for="p in positions" :key="p.symbol">
          <td><strong>{{ p.symbol }}</strong></td>
          <td>{{ parseFloat(p.positionAmt) > 0 ? '📈 多' : '📉 空' }}</td>
          <td>{{ Math.abs(parseFloat(p.positionAmt)).toFixed(4) }}</td>
          <td>{{ formatNum(p.entryPrice) }}</td>
          <td>{{ formatNum(p.markPrice) }}</td>
          <td>{{ p.leverage || '?' }}x</td>
          <td>{{ (Math.abs(parseFloat(p.positionAmt)) * parseFloat(p.markPrice)).toFixed(2) }}</td>
          <td :class="parseFloat(p.unRealizedProfit) >= 0 ? 'pnl-pos' : 'pnl-neg'">{{ parseFloat(p.unRealizedProfit).toFixed(2) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
defineProps({ positions: { type: Array, default: () => [] } })
function formatNum(v) { const n = parseFloat(v); return isNaN(n) ? '—' : n.toFixed(4) }
</script>

<style scoped>
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; color: var(--text-dim); font-weight: 500; padding: 8px 6px; border-bottom: 1px solid var(--border); }
td { padding: 6px 6px; border-bottom: 1px solid rgba(255,255,255,0.03); white-space: nowrap; }
.pnl-pos { color: var(--green); }
.pnl-neg { color: var(--red); }
.empty-state { text-align: center; padding: 32px; color: var(--text-dim); }
</style>
