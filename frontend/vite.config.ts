import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// In Docker the API proxy points at the backend service; on a host run it is localhost.
const apiTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  // "frontend" is the Compose service name, used by the end-to-end tests.
  server: { host: true, port: 5173, allowedHosts: ['localhost', 'frontend'], proxy: { '/api': apiTarget } },
})
