import { defineStore } from 'pinia'
import { api } from '../api/client.js'

export const useTradingStore = defineStore('trading', {
  state: () => ({
    // 仪表盘状态
    monitoring: false,
    stopLossTriggered: false,
    positions: [],
    totalPnl: 0,
    totalPnlFormatted: '+0.00',
    totalNotional: 0,
    totalEntryValue: 0,
    account: {},
    lastCheckTime: null,
    totalChecks: 0,
    threshold: 5,
    thresholdType: 'percent',
    effectiveThresholdFormatted: '+0.00',
    groups: [],
    dryRun: true,
    testnet: false,
    hasApiKey: false,
    // 设置
    apiKeyMasked: '',
    proxy: '',
    checkInterval: 5,
    hasAuthPassword: false,
    // 日志
    logs: [],
  }),

  actions: {
    async fetchStatus() {
      const s = await api.getStatus()
      Object.assign(this, {
        monitoring: s.monitoring,
        stopLossTriggered: s.stop_loss_triggered,
        positions: s.positions,
        totalPnl: s.total_pnl,
        totalPnlFormatted: s.total_pnl_formatted,
        totalNotional: s.total_notional,
        totalEntryValue: s.total_entry_value,
        account: s.account,
        lastCheckTime: s.last_check_time,
        totalChecks: s.total_checks,
        threshold: s.threshold,
        thresholdType: s.threshold_type,
        effectiveThresholdFormatted: s.effective_threshold_formatted,
        groups: s.groups || [],
        dryRun: s.dry_run,
        testnet: s.testnet,
        hasApiKey: s.has_api_key,
      })
    },

    async fetchSettings() {
      const s = await api.getSettings()
      Object.assign(this, {
        apiKeyMasked: s.api_key_masked,
        proxy: s.proxy,
        checkInterval: s.check_interval_seconds,
        threshold: s.stop_loss_threshold,
        thresholdType: s.threshold_type,
        dryRun: s.dry_run,
        hasAuthPassword: s.has_auth_password,
      })
    },

    addLog(level, msg) {
      this.logs.push({ level, msg, time: new Date().toLocaleTimeString() })
      if (this.logs.length > 200) this.logs.shift()
    },

    // SSE 事件处理
    handleSSEEvent(event, data) {
      switch (event.type) {
        case 'position_update':
          const d = JSON.parse(data)
          this.positions = d.positions || []
          this.totalPnl = d.total_pnl
          this.totalPnlFormatted = d.total_pnl_formatted
          this.totalNotional = d.total_notional
          this.totalEntryValue = d.total_entry_value
          this.lastCheckTime = d.time
          break
        case 'stop_loss_triggered':
          this.stopLossTriggered = true
          this.monitoring = false
          this.addLog('error', '🚨 止损触发!')
          break
        case 'emergency_close': {
          const d = JSON.parse(data)
          this.addLog('warn', `🔥 紧急清仓: 成功 ${d.success}, 失败 ${d.failed}`)
          break
        }
        case 'error': {
          const d = JSON.parse(data)
          this.addLog('error', d.message)
          break
        }
      }
    }
  }
})
