import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',  // Vite 8 默认只绑 ::1,显式绑定与 proxy target 一致
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
