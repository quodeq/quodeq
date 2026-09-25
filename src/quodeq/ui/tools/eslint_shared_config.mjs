// Shared `files`/`ignores`/`languageOptions` block for the two gates that
// scan the exact same file set with the same JS/JSX parser options:
// eslint.magic-strings.config.js and eslint.vocab.config.js. Kept as data
// (spread into each config's own object), not a whole config object, so each
// gate still owns its own `plugins`/`rules` and can be consumed independently
// with inline config disabled.
export const SRC_JS_JSX_BASE = {
  files: ['src/**/*.js', 'src/**/*.jsx'],
  ignores: [
    'src/vocab/**',
    'src/strings/**',
    'src/**/*.test.js',
    'src/**/*.test.jsx',
    'src/**/*.fixtures.js',
    'src/**/*.fixtures.jsx',
  ],
  languageOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    parserOptions: { ecmaFeatures: { jsx: true } },
  },
};
