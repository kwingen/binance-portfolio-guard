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
  // 检查是否需要 setup
  if (to.name !== 'Setup') {
    try {
      const res = await fetch('/api/auth/status', { credentials: 'include' })
      const data = await res.json()
      if (data.setup_needed) return next('/setup')
    } catch (_) {}
  }

  if (to.meta.requiresAuth) {
    try {
      const res = await fetch('/api/auth/me', { credentials: 'include' })
      if (res.ok) return next()
    } catch (_) {}
    next('/login')
  } else {
    next()
  }
})

export default router
