// Config fragments the UI's eslint configs share. Kept as data (spread or
// assigned into each config's own object), not whole config objects, so each
// gate still owns its own `plugins`/`rules` and can be consumed independently
// with inline config disabled.

// Parser options for the app's ES modules, JSX included; every gate that
// parses src/ uses them.
export const JSX_MODULE_LANGUAGE_OPTIONS = {
  ecmaVersion: 'latest',
  sourceType: 'module',
  parserOptions: { ecmaFeatures: { jsx: true } },
};

// eslint-plugin-react settings: read the React version from the install.
export const REACT_SETTINGS = { react: { version: 'detect' } };

// `files`/`ignores`/`languageOptions` for the two gates that scan the exact
// same file set: eslint.magic-strings.config.js and eslint.vocab.config.js.
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
  languageOptions: JSX_MODULE_LANGUAGE_OPTIONS,
};
