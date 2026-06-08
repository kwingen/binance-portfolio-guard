import { defineStore } from 'pinia'
import { api } from '../api/client.js'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('access_token') || '',
    error: '',
  }),
  getters: {
    isLoggedIn: (state) => !!state.token,
  },
  actions: {
    async login(password) {
      this.error = ''
      try {
        const res = await api.login(password)
        this.token = res.access_token
        localStorage.setItem('access_token', res.access_token)
        return true
      } catch (e) {
        this.error = e.message
        return false
      }
    },
    logout() {
      this.token = ''
      localStorage.removeItem('access_token')
    }
  }
})
