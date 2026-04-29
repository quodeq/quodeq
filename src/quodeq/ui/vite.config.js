// Vite configuration for the Quodeq web UI.
// Dev server proxies /api to the local Node.js server (VITE_API_TARGET).
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const DEFAULT_API_TARGET = 'http://localhost:4173';
const DEFAULT_DEV_PORT = 5173;

export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    include: ['@chenglou/pretext'],
  },
  build: {
    outDir: process.env.QUODEQ_BUILD_OUTDIR || '../static',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom'],
          'vendor-d3': ['d3-hierarchy'],
          'vendor-markdown': ['react-markdown', 'remark-gfm'],
        },
      },
    },
  },
  server: {
    port: Number(process.env.VITE_PORT) || DEFAULT_DEV_PORT,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || DEFAULT_API_TARGET,
        changeOrigin: true
      }
    }
  }
});
