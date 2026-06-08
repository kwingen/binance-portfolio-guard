<template>
  <div class="setup-page">
    <div class="setup-box">
      <h2>🔐 首次使用 · 设置管理员密码</h2>
      <p class="intro">
        欢迎使用 Binance 总仓位止损面板。<br>
        请设置一个访问密码，后续通过此密码登录。<br>
        <span class="hint">API Key 可以稍后在面板设置中填写。</span>
      </p>
      <form @submit.prevent="handleSetup">
        <div class="form-group">
          <label>管理员密码</label>
          <input v-model="password" type="password" placeholder="至少 6 位" autofocus>
        </div>
        <div class="form-group">
          <label>确认密码</label>
          <input v-model="confirm" type="password" placeholder="再次输入">
        </div>
        <p v-if="error" class="error">{{ error }}</p>
        <button type="submit" class="btn" :disabled="loading">
          {{ loading ? '设置中...' : '设置密码并进入' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client.js'

const router = useRouter()
const password = ref('')
const confirm = ref('')
const error = ref('')
const loading = ref(false)

async function handleSetup() {
  error.value = ''
  if (password.value.length < 6) {
    error.value = '密码至少 6 位'
    return
  }
  if (password.value !== confirm.value) {
    error.value = '两次输入的密码不一致'
    return
  }

  loading.value = true
  try {
    const res = await api.setup(password.value)
    localStorage.setItem('access_token', res.access_token)
    router.push('/')
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
  padding: 40px; width: 100%; max-width: 420px;
}
.setup-box h2 { font-size: 20px; margin-bottom: 16px; text-align: center; }
.intro { text-align: center; font-size: 14px; color: var(--text-dim); margin-bottom: 24px; line-height: 1.6; }
.hint { color: var(--orange); font-size: 12px; }
.form-group { margin-bottom: 16px; }
.form-group label { display: block; color: var(--text-dim); font-size: 12px; margin-bottom: 6px; }
.form-group input {
  width: 100%; background: var(--bg); border: 1px solid var(--border); color: var(--text);
  padding: 12px; border-radius: 8px; font-size: 15px;
}
.btn {
  width: 100%; padding: 12px; border: none; border-radius: 8px; font-size: 15px;
  font-weight: 600; cursor: pointer; background: var(--blue); color: #fff;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.error { color: var(--red); font-size: 13px; text-align: center; margin-bottom: 12px; }
</style>
