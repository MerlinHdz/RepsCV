import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: false },
      '/ws': { target: 'ws://localhost:8000', ws: true, changeOrigin: false },
    },
  },
  test: { environment: 'jsdom', include: ['src/*.test.tsx'] },
})
