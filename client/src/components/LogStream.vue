<template>
  <div class="log-stream" ref="logEl">
    <div v-for="(l, i) in logs" :key="i" :class="l.level">
      [{{ l.time }}] {{ l.msg }}
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
defineProps({ logs: { type: Array, default: () => [] } })
const logEl = ref(null)

watch(() => arguments[0]?.logs?.length, async () => {
  await nextTick()
  if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
})
</script>

<style scoped>
.log-stream {
  background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
  padding: 10px; max-height: 200px; overflow-y: auto;
  font-family: 'SF Mono', 'Fira Code', Consolas, monospace; font-size: 12px;
  color: var(--text-dim);
}
.error { color: var(--red); }
.warn { color: var(--yellow); }
.info { color: var(--blue); }
</style>
