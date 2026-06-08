import { createRouter, createWebHistory } from 'vue-router'
import SetupView from '../components/SetupView.vue'
import LoginView from '../components/LoginView.vue'
import DashboardView from '../components/DashboardView.vue'

const routes = [
  { path: '/setup', name: 'Setup', component: SetupView },
  { path: '/login', name: 'Login', component: LoginView },
  { path: '/', name: 'Dashboard', component: DashboardView, meta: { requiresAuth: true } },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(async (to, from, next) => {
  const token = localStorage.getItem('access_token')

  // 检查是否需要 setup（公开端点）
  if (to.name !== 'Setup') {
    try {
      const res = await fetch('/api/auth/status')
      const data = await res.json()
      if (data.setup_needed) {
        return next('/setup')
      }
    } catch (_) {
      // 网络错误，允许继续（可能是后端未启动）
    }
  }

  if (to.meta.requiresAuth && !token) {
    next('/login')
  } else if (to.name === 'Login' && token) {
    next('/')
  } else if (to.name === 'Setup' && token) {
    // 已登录就不需要再 setup
    next('/')
  } else {
    next()
  }
})

export default router
