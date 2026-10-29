import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The backend (Flask) runs separately, typically on http://127.0.0.1:5000
// In dev we proxy /api and /socket.io to it so cookies stay same-site
// and we avoid needing permissive CORS during local development.
const BACKEND_ORIGIN = process.env.VITE_BACKEND_ORIGIN || 'http://127.0.0.1:5000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: BACKEND_ORIGIN,
        changeOrigin: true,
        secure: false,
      },
      '/socket.io': {
        target: BACKEND_ORIGIN,
        changeOrigin: true,
        secure: false,
        ws: true,
      },
    },
  },
})
