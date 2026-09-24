// Naming ratchet: module constants are UPPER_SNAKE_CASE, module functions
// camelCase (PascalCase components in .jsx). The rule is
// tools/naming_rule.mjs; there is no TypeScript here, so
// @typescript-eslint/naming-convention is not an option.
//
// Consumed by tools/check_naming.mjs with inline config disabled: the only
// way to grandfather a violation is tools/naming_baseline.json, which landed
// empty and may only shrink.
import namingRule from './tools/naming_rule.mjs';

export default [
  {
    files: ['src/**/*.{js,jsx}'],
    ignores: ['src/**/*.{test,fixtures}.{js,jsx}'],
    plugins: { naming: { rules: { 'module-names': namingRule } } },
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: { 'naming/module-names': 'error' },
  },
];
