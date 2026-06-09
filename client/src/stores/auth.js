import { defineStore } from 'pinia'
import { api } from '../api/client.js'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    loggedIn: false,
    error: '',
  }),
  actions: {
    async checkAuth() {
      try {
        await api.getMe()
        this.loggedIn = true
      } catch {
        this.loggedIn = false
      }
    },
    async login(password) {
      this.error = ''
      try {
        await api.login(password)
        this.loggedIn = true
        return true
      } catch (e) {
        this.error = e.message
        return false
      }
    },
    async logout() {
      try { await api.logout() } catch (_) {}
      this.loggedIn = false
    }
  }
})
