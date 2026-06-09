const BASE = ''

async function request(method, path, body) {
  const headers = { 'Content-Type': 'application/json' }
  const csrf = getCsrfToken()
  if (csrf) headers['X-CSRF-Token'] = csrf

  const res = await fetch(`${BASE}${path}`, {
    method, headers,
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'include',  // Cookie 自动携带
  })

  if (res.status === 401 || res.status === 403) {
    const isAuthEndpoint = path.startsWith('/api/auth/')
    if (!isAuthEndpoint) {
      window.location.href = '/login'
    }
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || '认证失败')
  }

  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || '请求失败')
  return data
}

function getCsrfToken() {
  return document.cookie.split('; ').find(r => r.startsWith('sl_csrf='))?.split('=')[1] || ''
}

export const api = {
  login: (password) => request('POST', '/api/auth/login', { password }),
  logout: () => request('POST', '/api/auth/logout'),
  setup: (password, token) => request('POST', '/api/auth/setup', { password, setup_token: token }),
  getAuthStatus: () => request('GET', '/api/auth/status'),
  getMe: () => request('GET', '/api/auth/me'),
  getStatus: () => request('GET', '/api/status'),
  getSettings: () => request('GET', '/api/settings'),
  saveSettings: (data) => request('POST', '/api/settings', data),
  applyConfig: (data) => request('POST', '/api/config', data),
  startMonitor: () => request('POST', '/api/monitor/start'),
  stopMonitor: () => request('POST', '/api/monitor/stop'),
  emergencyClose: (confirm) => request('POST', '/api/emergency-close', { confirm }),
  changePassword: (oldPw, newPw) => request('POST', '/api/auth/change-password', { old_password: oldPw, new_password: newPw }),
}
