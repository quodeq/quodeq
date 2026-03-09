// Vite configuration for the Quodeq web UI.
// Dev server proxies /api to the local Node.js server (VITE_API_TARGET).
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.VITE_PORT) || 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://localhost:4173',
        changeOrigin: true
      }
    }
  }
});
