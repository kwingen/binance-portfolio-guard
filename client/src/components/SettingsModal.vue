<template>
  <div class="overlay" @click.self="$emit('close')">
    <div class="modal">
      <h2>⚙️ 设置 <button class="close-btn" @click="$emit('close')">×</button></h2>

      <div class="form-row">
        <div class="form-group"><label>API Key</label><input v-model="form.api_key" placeholder="币安 API Key"></div>
        <div class="form-group"><label>API Secret</label><input v-model="form.api_secret" type="password" placeholder="留空不修改"></div>
      </div>
      <div class="form-row" v-if="form.api_key || form.api_secret">
        <div class="form-group"><label>当前密码（验证身份）</label><input v-model="form.current_password" type="password" placeholder="修改 API 需输入密码"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>网络</label><select v-model="form.testnet"><option :value="false">主网</option><option :value="true">测试网</option></select></div>
        <div class="form-group"><label>代理</label><input v-model="form.proxy" placeholder="http://127.0.0.1:7890"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>新密码（留空不修改）</label><input v-model="form.new_password" type="password" placeholder="设置新密码"></div>
        <div class="form-group"><label>确认新密码</label><input v-model="form.confirm_password" type="password" placeholder="再次输入"></div>
      </div>
      <div class="form-row" v-if="form.new_password || form.confirm_password">
        <div class="form-group"><label>当前密码（修改密码需验证）</label><input v-model="form.password_old" type="password" placeholder="输入当前密码"></div>
      </div>
      <div v-if="form.new_password" class="strength-meter" style="margin-bottom:12px">
        <div class="checks">
          <span :class="pwChecks.length">最少 8 位</span>
          <span :class="pwChecks.upper">大写字母</span>
          <span :class="pwChecks.lower">小写字母</span>
          <span :class="pwChecks.digit">数字</span>
          <span :class="pwChecks.special">特殊字符</span>
        </div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>止损阈值</label><input v-model.number="form.stop_loss_threshold" type="number" step="0.1"></div>
        <div class="form-group"><label>检查间隔 (秒)</label><input v-model.number="form.check_interval_seconds" type="number" min="2" max="300"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>阈值类型</label>
          <select v-model="form.threshold_type">
            <option value="percent">% (开仓成本百分比)</option>
            <option value="usd">USDT</option>
          </select>
        </div>
        <div class="form-group"></div>
      </div>

      <!-- 仓位分组编辑器 -->
      <div style="margin-bottom:12px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
          <label style="color:var(--text-dim);font-size:12px">📦 仓位分组（独立止损）</label>
          <button type="button" class="btn btn-xs btn-green" @click="addGroup">+ 添加分组</button>
        </div>
        <div v-for="(group, gi) in form.portfolios" :key="gi" style="border:1px solid var(--border);border-radius:6px;padding:10px;margin-bottom:8px">
          <div class="form-row">
            <div class="form-group"><label>名称</label><input v-model="group.name" style="font-size:12px"></div>
            <div class="form-group"><label>止损</label><div style="display:flex;gap:4px"><input v-model.number="group.stop_loss_threshold" type="number" step="0.1" style="flex:1;font-size:12px"><select v-model="group.threshold_type" style="width:70px;font-size:11px"><option value="percent">%</option><option value="usd">USDT</option></select></div></div>
          </div>
          <div style="margin-bottom:6px">
            <span style="font-size:11px;color:var(--text-dim)">仓位:</span>
            <span v-for="(pos, pi) in group.positions" :key="pi" style="font-size:11px;background:var(--bg);padding:2px 6px;border-radius:4px;margin:0 2px">
              {{ pos.symbol }} {{ pos.direction === 'long' ? '多' : '空' }}
              <button type="button" @click="group.positions.splice(pi,1)" style="cursor:pointer;border:none;background:none;color:var(--red);font-size:11px">×</button>
            </span>
          </div>
          <div class="form-row">
            <div class="form-group"><input v-model="newPosSymbol[gi]" placeholder="交易对 (如 BTCUSDT)" style="font-size:11px"></div>
            <div class="form-group"><select v-model="newPosDir[gi]" style="font-size:11px"><option value="long">多</option><option value="short">空</option></select></div>
            <button type="button" class="btn btn-xs btn-blue" @click="addPosition(gi)">添加</button>
          </div>
          <button type="button" class="btn btn-xs btn-red" @click="form.portfolios.splice(gi,1)" style="margin-top:4px">删除分组</button>
        </div>
      </div>

      <div class="form-actions">
        <button class="btn btn-blue" @click="save" :disabled="saving">💾 {{ saving ? '保存中...' : '保存设置' }}</button>
        <span class="status" :class="statusClass">{{ statusMsg }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, computed, onMounted } from 'vue'
import { api } from '../api/client.js'
import { useTradingStore } from '../stores/trading.js'

const emit = defineEmits(['close', 'saved'])
const store = useTradingStore()

const form = reactive({
  api_key: '', api_secret: '', testnet: false, proxy: '',
  new_password: '', confirm_password: '', password_old: '',
  current_password: '', check_interval_seconds: 5,
  stop_loss_threshold: 5, threshold_type: 'percent',
  portfolios: [],
})

const pwChecks = computed(() => ({
  length: form.new_password.length >= 8,
  upper: /[A-Z]/.test(form.new_password),
  lower: /[a-z]/.test(form.new_password),
  digit: /[0-9]/.test(form.new_password),
  special: /[!@#$%^&*()\-_=+[\]{}|;:',.<>?/`~]/.test(form.new_password),
}))

const newPosSymbol = reactive({})
const newPosDir = reactive({})

const saving = ref(false)
const statusMsg = ref('')
const statusClass = ref('')

onMounted(async () => {
  const s = await api.getSettings()
  form.api_key = s.api_key_masked
  form.testnet = store.testnet
  form.proxy = store.proxy || ''
  form.check_interval_seconds = store.checkInterval
  form.stop_loss_threshold = store.threshold
  form.threshold_type = store.thresholdType
  form.portfolios = JSON.parse(JSON.stringify(s.portfolios || []))
})

function addGroup() {
  form.portfolios.push({
    name: 'Group ' + (form.portfolios.length + 1),
    positions: [],
    stop_loss_threshold: 5,
    threshold_type: 'percent',
    enabled: true,
  })
}
function addPosition(gi) {
  const sym = (newPosSymbol[gi] || '').trim().toUpperCase()
  if (!sym) return
  form.portfolios[gi].positions.push({ symbol: sym, direction: newPosDir[gi] || 'long' })
  newPosSymbol[gi] = ''
}

async function save() {
  saving.value = true
  statusMsg.value = '保存中...'
  statusClass.value = ''
  try {
    // 改密码（独立的 API）
    if (form.new_password) {
      if (form.new_password !== form.confirm_password) {
        throw new Error('两次输入的密码不一致')
      }
      if (!Object.values(pwChecks.value).every(Boolean)) {
        throw new Error('密码不符合安全要求')
      }
      if (!form.password_old) {
        throw new Error('请输入当前密码')
      }
      await api.changePassword(form.password_old, form.new_password)
    }

    const data = {}
    if (form.api_key && !form.api_key.includes('****')) data.api_key = form.api_key
    if (form.api_secret && !form.api_secret.includes('****')) data.api_secret = form.api_secret
    if (form.current_password) data.current_password = form.current_password
    data.testnet = form.testnet
    data.proxy = form.proxy || null
    data.check_interval_seconds = form.check_interval_seconds
    data.stop_loss_threshold = form.stop_loss_threshold
    data.threshold_type = form.threshold_type
    if (form.portfolios && form.portfolios.length) data.portfolios = form.portfolios

    await api.saveSettings(data)
    statusMsg.value = '✅ 已保存'
    statusClass.value = 'ok'
    // 清除密码字段
    form.new_password = ''; form.confirm_password = ''; form.password_old = ''
    setTimeout(() => emit('saved'), 500)
  } catch (e) {
    statusMsg.value = '❌ ' + e.message
    statusClass.value = 'err'
  }
  saving.value = false
  setTimeout(() => { statusMsg.value = '' }, 5000)
}
</script>

<style scoped>
.overlay {
  position: fixed; top: 0; left: 0; width: 100%; height: 100%;
  background: rgba(0,0,0,0.7); z-index: 100;
  display: flex; align-items: center; justify-content: center;
}
.modal {
  background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px;
  padding: 24px; width: 100%; max-width: 520px; max-height: 85vh; overflow-y: auto;
}
.modal h2 { font-size: 18px; margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center; }
.close-btn { cursor: pointer; color: var(--text-dim); font-size: 24px; border: none; background: none; }
.form-row { display: flex; gap: 10px; margin-bottom: 12px; }
.form-group { flex: 1; }
.form-group label { display: block; color: var(--text-dim); font-size: 12px; margin-bottom: 4px; }
.form-group input, .form-group select {
  width: 100%; background: var(--bg); border: 1px solid var(--border);
  color: var(--text); padding: 8px 10px; border-radius: 6px; font-size: 13px;
}
.form-actions { display: flex; align-items: center; gap: 8px; margin-top: 12px; }
.btn { padding: 8px 16px; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-blue { background: var(--blue); color: #fff; }
.status { font-size: 12px; }
.status.ok { color: var(--green); }
.status.err { color: var(--red); }
.strength-meter .checks { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.strength-meter .checks span {
  font-size: 10px; padding: 2px 6px; border-radius: 8px;
  background: rgba(255,255,255,0.05); color: var(--text-dim);
}
.strength-meter .checks span.true { background: rgba(0,200,83,0.15); color: var(--green); }
</style>
