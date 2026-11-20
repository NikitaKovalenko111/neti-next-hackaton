import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'CHAT_')
  const target = env.CHAT_API_TARGET || 'http://localhost:3001'
  const proxy = { target, changeOrigin: true }

  return {
    plugins: [react()],
    server: {
      port: 5137,
      proxy: {
        '/api': proxy,
        '/health': proxy,
      },
    },
  }
})
