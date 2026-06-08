<template>
  <div class="trade-panel card">
    <h3>📈 开仓下单</h3>
    <div class="form-row">
      <div class="form-group">
        <label>交易对</label>
        <input v-model="symbol" placeholder="BTCUSDT" @input="s = s.toUpperCase()" style="text-transform:uppercase">
      </div>
      <div class="form-group">
        <label>方向</label>
        <div class="btn-group">
          <button :class="['btn-sm', side === 'BUY' ? 'btn-green' : 'btn-ghost']" @click="side = 'BUY'">📈 多</button>
          <button :class="['btn-sm', side === 'SELL' ? 'btn-red' : 'btn-ghost']" @click="side = 'SELL'">📉 空</button>
        </div>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>类型</label>
        <div class="btn-group">
          <button :class="['btn-sm', orderType === 'MARKET' ? 'btn-blue' : 'btn-ghost']" @click="orderType = 'MARKET'">市价</button>
          <button :class="['btn-sm', orderType === 'LIMIT' ? 'btn-blue' : 'btn-ghost']" @click="orderType = 'LIMIT'">限价</button>
        </div>
      </div>
      <div class="form-group" v-if="orderType === 'LIMIT'">
        <label>价格</label>
        <input v-model.number="price" type="number" step="0.01" placeholder="限价">
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>数量</label>
        <input v-model.number="quantity" type="number" step="0.001" placeholder="0.001">
      </div>
      <div class="form-group">
        <label>杠杆</label>
        <input v-model.number="leverage" type="number" min="1" max="125">
      </div>
    </div>
    <button class="btn" :class="side === 'BUY' ? 'btn-green' : 'btn-red'" @click="submit" :disabled="submitting">
      {{ submitting ? '下单中...' : (side === 'BUY' ? '📈 做多' : '📉 做空') + ' ' + symbol.toUpperCase() }}
    </button>
    <p v-if="status" class="status" :class="statusType">{{ status }}</p>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { api } from '../api/client.js'
import { useTradingStore } from '../stores/trading.js'

const store = useTradingStore()
const symbol = ref('BTCUSDT')
const side = ref('BUY')
const orderType = ref('MARKET')
const quantity = ref(0.001)
const leverage = ref(10)
const price = ref(null)
const submitting = ref(false)
const status = ref('')
const statusType = ref('')

async function submit() {
  if (!symbol.value || quantity.value <= 0) {
    status.value = '请填写交易对和数量'; statusType.value = 'err'; return
  }
  submitting.value = true; status.value = ''
  try {
    const res = await fetch('/api/order', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + localStorage.getItem('access_token') },
      body: JSON.stringify({
        symbol: symbol.value.toUpperCase(),
        side: side.value,
        order_type: orderType.value,
        quantity: quantity.value,
        price: orderType.value === 'LIMIT' ? price.value : undefined,
        leverage: leverage.value,
      })
    })
    const data = await res.json()
    if (res.ok) {
      const dry = data.dry_run ? ' [DRY RUN]' : ''
      status.value = `✅ 下单成功${dry}`; statusType.value = 'ok'
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
</script>

<style scoped>
.trade-panel { margin-top: 12px; }
.form-row { display: flex; gap: 10px; margin-bottom: 10px; }
.form-group { flex: 1; }
.form-group label { display: block; color: var(--text-dim); font-size: 12px; margin-bottom: 4px; }
.form-group input {
  width: 100%; background: var(--bg); border: 1px solid var(--border);
  color: var(--text); padding: 8px; border-radius: 6px; font-size: 13px;
}
.btn-group { display: flex; gap: 4px; }
.btn-sm {
  flex: 1; padding: 8px; border: 1px solid var(--border); border-radius: 6px;
  font-size: 13px; cursor: pointer; background: transparent; color: var(--text);
}
.btn-green { background: var(--green) !important; color: #000 !important; border-color: var(--green) !important; }
.btn-red { background: var(--red) !important; color: #fff !important; border-color: var(--red) !important; }
.btn-blue { background: var(--blue) !important; color: #fff !important; border-color: var(--blue) !important; }
.btn-ghost { background: transparent; color: var(--text-dim); }
.btn {
  width: 100%; padding: 12px; border: none; border-radius: 8px; font-size: 15px;
  font-weight: 600; cursor: pointer; margin-top: 4px;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.status { font-size: 12px; margin-top: 8px; text-align: center; }
.status.ok { color: var(--green); }
.status.err { color: var(--red); }
</style>
