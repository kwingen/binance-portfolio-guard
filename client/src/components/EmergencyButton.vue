<template>
  <div style="margin-top:16px">
    <button class="emergency-btn" :class="{ confirming }" @click="handleClick" :disabled="executing">
      {{ label }}
    </button>
    <p style="font-size:11px;color:var(--text-dim);margin-top:4px;text-align:center">
      需要双击确认 · 市价单平掉所有仓位
    </p>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { api } from '../api/client.js'
import { useTradingStore } from '../stores/trading.js'

const store = useTradingStore()
const confirming = ref(false)
const executing = ref(false)
let confirmTimer = null

const label = computed(() => {
  if (executing.value) return '执行中...'
  if (confirming.value) return '⚠️ 再次点击确认清仓!'
  return '🚨 紧急一键清仓'
})

function handleClick() {
  if (!confirming.value) {
    confirming.value = true
    confirmTimer = setTimeout(() => { confirming.value = false }, 5000)
    return
  }
  clearTimeout(confirmTimer)
  confirming.value = false
  executing.value = true
  api.emergencyClose(true).then(res => {
    if (res.error) store.addLog('error', '清仓失败: ' + res.error)
  }).catch(e => {
    store.addLog('error', e.message)
  }).finally(() => {
    executing.value = false
  })
}
</script>

<style scoped>
.emergency-btn {
  width: 100%; padding: 16px; font-size: 18px; background: var(--red);
  color: #fff; border: none; border-radius: 10px; cursor: pointer; font-weight: 700;
}
.emergency-btn.confirming { background: #b71c1c; animation: pulse 0.5s infinite; }
.emergency-btn:disabled { opacity: 0.5; cursor: not-allowed; }
@keyframes pulse { 0%,100% { opacity: 1 } 50% { opacity: 0.4 } }
</style>
