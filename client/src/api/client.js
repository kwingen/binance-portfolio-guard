const BASE = ''

function token() { return localStorage.getItem('access_token') }

async function request(method, path, body) {
  const headers = { 'Content-Type': 'application/json' }
  const t = token()
  if (t) headers['Authorization'] = `Bearer ${t}`

  const res = await fetch(`${BASE}${path}`, {
    method, headers,
    body: body ? JSON.stringify(body) : undefined,
  })

  if (res.status === 401) {
    localStorage.removeItem('access_token')
    window.location.href = '/login'
    throw new Error('登录已过期')
  }

  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || '请求失败')
  return data
}

export const api = {
  login: (password) => request('POST', '/api/auth/login', { password }),
  setup: (password) => request('POST', '/api/auth/setup', { password }),
  getAuthStatus: () => request('GET', '/api/auth/status'),
  getStatus: () => request('GET', '/api/status'),
  getSettings: () => request('GET', '/api/settings'),
  saveSettings: (data) => request('POST', '/api/settings', data),
  applyConfig: (data) => request('POST', '/api/config', data),
  startMonitor: () => request('POST', '/api/monitor/start'),
  stopMonitor: () => request('POST', '/api/monitor/stop'),
  emergencyClose: (confirm) => request('POST', '/api/emergency-close', { confirm }),
  changePassword: (oldPw, newPw) => request('POST', '/api/auth/change-password', { old_password: oldPw, new_password: newPw }),
}
