import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    // `@/` points at src/, as it did under Next.js
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    // Local dev only. The backend's CORS_ORIGINS default allows http://localhost:3000,
    // so the dev server keeps the port the Next.js app used.
    port: 3000,
  },
})
