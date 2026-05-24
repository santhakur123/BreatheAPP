import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  define: {
    'import.meta.env.VITE_API_URL': JSON.stringify(
      process.env.VITE_API_URL || 'https://breathe-esg-backend-0cws.onrender.com/api'
    )
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000'
    }
  }
})
