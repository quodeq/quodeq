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
    //
    // Exception: `api/terminal.test.js` imports `terminal.js`, which reads
    // `import.meta.env` (via request.js). That's only defined under Vite, so
    // this one file is carved out of `npm test`'s node:test glob (see the
    // "test" script in package.json) and runs here under vitest instead.
    include: ['**/*.test.jsx', 'src/api/terminal.test.js'],
  },
});
