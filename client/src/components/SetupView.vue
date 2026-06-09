<template>
  <div class="setup-page">
    <div class="setup-box">
      <h2>🔐 首次使用 · 设置管理员密码</h2>
      <p class="intro">
        请在服务器控制台找到 <strong>Setup Token</strong>，<br>
        然后设置一个符合安全要求的密码。
      </p>

      <form @submit.prevent="handleSetup">
        <!-- Setup Token -->
        <div class="form-group">
          <label>Setup Token</label>
          <input v-model="setupToken" type="text" placeholder="服务器控制台输出的 token" autofocus>
          <p class="hint">
            ⚠️ 此 token 仅显示在服务器启动日志中，24 位随机字符串
          </p>
        </div>

        <!-- 密码 -->
        <div class="form-group">
          <label>管理员密码</label>
          <input v-model="password" type="password" placeholder="至少 8 位，包含大小写字母+数字+特殊字符">
        </div>
        <div class="form-group">
          <label>确认密码</label>
          <input v-model="confirm" type="password" placeholder="再次输入">
        </div>

        <!-- 实时强度提示 -->
        <div v-if="password" class="strength-meter">
          <div class="checks">
            <span :class="checks.length">最少 8 位</span>
            <span :class="checks.upper">大写字母</span>
            <span :class="checks.lower">小写字母</span>
            <span :class="checks.digit">数字</span>
            <span :class="checks.special">特殊字符</span>
          </div>
        </div>

        <p v-if="error" class="error">{{ error }}</p>
        <button type="submit" class="btn" :disabled="loading || !allChecksPassed">
          {{ loading ? '设置中...' : '设置密码并进入' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client.js'

const router = useRouter()
const setupToken = ref('')
const password = ref('')
const confirm = ref('')
const error = ref('')
const loading = ref(false)

const checks = computed(() => ({
  length: password.value.length >= 8,
  upper: /[A-Z]/.test(password.value),
  lower: /[a-z]/.test(password.value),
  digit: /[0-9]/.test(password.value),
  special: /[!@#$%^&*()\-_=+[\]{}|;:',.<>?/`~]/.test(password.value),
}))

const allChecksPassed = computed(() =>
  Object.values(checks.value).every(Boolean) && password.value === confirm.value && confirm.value !== ''
)

async function handleSetup() {
  error.value = ''
  if (!setupToken.value.trim()) {
    error.value = '请输入 Setup Token（服务器控制台可见）'
    return
  }
  if (!allChecksPassed.value) {
    if (password.value !== confirm.value) {
      error.value = '两次输入的密码不一致'
      return
    }
    error.value = '密码不符合安全要求，请检查上方提示'
    return
  }

  loading.value = true
  try {
    const res = await api.setup(password.value, setupToken.value.trim())
    if (res.ok) router.push('/')
  } catch (e) {
    error.value = e.message
  }
  loading.value = false
}
</script>

<style scoped>
.setup-page { display: flex; align-items: center; justify-content: center; min-height: 100vh; }
.setup-box {
  background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px;
  padding: 40px; width: 100%; max-width: 440px;
}
.setup-box h2 { font-size: 20px; margin-bottom: 12px; text-align: center; }
.intro { text-align: center; font-size: 14px; color: var(--text-dim); margin-bottom: 24px; line-height: 1.6; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; color: var(--text-dim); font-size: 12px; margin-bottom: 6px; }
.form-group input {
  width: 100%; background: var(--bg); border: 1px solid var(--border); color: var(--text);
  padding: 10px; border-radius: 8px; font-size: 14px; font-family: inherit;
}
.hint { font-size: 11px; color: var(--orange); margin-top: 4px; }

.strength-meter { margin-bottom: 12px; }
.checks { display: flex; flex-wrap: wrap; gap: 6px; }
.checks span {
  font-size: 11px; padding: 3px 8px; border-radius: 10px;
  background: rgba(255,255,255,0.05); color: var(--text-dim);
  transition: all 0.2s;
}
.checks span.true { background: rgba(0,200,83,0.15); color: var(--green); }

.btn {
  width: 100%; padding: 12px; border: none; border-radius: 8px; font-size: 15px;
  font-weight: 600; cursor: pointer; background: var(--blue); color: #fff;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.error { color: var(--red); font-size: 13px; text-align: center; margin-bottom: 12px; }
</style>
