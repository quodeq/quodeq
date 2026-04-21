import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.js'],
    // Only discover component/JSX tests. Pure-JS utility tests in `.test.js`
    // files use Node's native `node:test` runner (see `npm test`) and must
    // be excluded here so vitest doesn't mis-report them as failed suites.
    include: ['**/*.test.jsx'],
  },
});
