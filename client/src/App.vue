<template>
  <div class="app-container">
    <router-view />
  </div>
</template>

<style>
:root {
  --bg: #0f1117; --card-bg: #1a1d27; --border: #2a2d37;
  --text: #e0e0e0; --text-dim: #888; --green: #00c853;
  --red: #ff1744; --blue: #448aff; --orange: #ff9100; --yellow: #ffd600;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: var(--bg); color: var(--text); min-height: 100vh;
}
input, select, button { font-family: inherit; }
</style>
