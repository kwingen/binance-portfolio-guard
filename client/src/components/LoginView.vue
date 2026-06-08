<template>
  <div class="login-page">
    <div class="login-box">
      <h2>🔐 Binance 止损面板</h2>
      <p v-if="error" class="error">{{ error }}</p>
      <form @submit.prevent="handleLogin">
        <div class="form-group">
          <label>密码</label>
          <input v-model="password" type="password" placeholder="请输入访问密码" autofocus>
        </div>
        <button type="submit" class="btn" :disabled="loading">
          {{ loading ? '登录中...' : '登 录' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const router = useRouter()
const auth = useAuthStore()
const password = ref('')
const error = ref('')
const loading = ref(false)

async function handleLogin() {
  loading.value = true
  error.value = ''
  const ok = await auth.login(password.value)
  if (ok) router.push('/')
  else error.value = auth.error
  loading.value = false
}
</script>

<style scoped>
.login-page {
  display: flex; align-items: center; justify-content: center; min-height: 100vh;
}
.login-box {
  background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px;
  padding: 40px; width: 100%; max-width: 380px;
}
.login-box h2 { font-size: 20px; margin-bottom: 24px; text-align: center; }
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
