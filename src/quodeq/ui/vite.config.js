// Vite configuration for the Quodeq web UI.
// Dev server proxies /api to the local Flask API server (VITE_API_TARGET).
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const DEFAULT_API_TARGET = 'http://localhost:7863';
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
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          if (id.includes('/react-dom/') || /\/react\//.test(id)) return 'vendor-react';
          if (id.includes('/d3-hierarchy/')) return 'vendor-d3';
          if (id.includes('/react-markdown/') || id.includes('/remark-gfm/')) return 'vendor-markdown';
          if (id.includes('/@tanstack/react-query')) return 'vendor-tanstack-query';
          if (id.includes('/@xterm/')) return 'vendor-xterm';
          return undefined;
        },
      },
    },
  },
  server: {
    port: Number(process.env.VITE_PORT) || DEFAULT_DEV_PORT,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || DEFAULT_API_TARGET,
        changeOrigin: true,
        ws: true
      }
    }
  }
});
