import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'CHAT_')
  const target = env.CHAT_API_TARGET || 'http://127.0.0.1:8080'
  const proxy = { target }

  return {
    plugins: [react()],
    server: {
      port: 5138,
      strictPort: true,
      proxy: {
        '/request': proxy,
        '/chats': proxy,
        '/register': proxy,
        '/login': proxy,
        '/health': proxy,
        '/ws': { ...proxy, ws: true },
      },
    },
  }
})
