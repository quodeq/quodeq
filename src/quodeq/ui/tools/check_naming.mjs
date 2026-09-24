#!/usr/bin/env node
// Ratchet gate for the UI naming style (eslint.naming.config.js). It landed
// at zero: tools/naming_baseline.json is empty and the ceiling is 0, so any
// new violation fails outright. tools/naming_rule.test.mjs pins both.
import { main } from './ratchet.mjs';

// NEVER raise without a justification reviewed in the PR that raises it.
const TOTAL_CEILING = 0;

main({
  script: 'check_naming.mjs',
  configPath: 'eslint.naming.config.js',
  baselinePath: 'tools/naming_baseline.json',
  rules: ['naming/module-names'],
  ceiling: TOTAL_CEILING,
  noun: 'naming violations',
  found: 'misnamed module constant(s) or function(s)',
  hint: 'Name a module constant that holds a literal or frozen object in UPPER_SNAKE_CASE, and a module function in camelCase (PascalCase for a .jsx component). Run `npx eslint --no-inline-config -c eslint.naming.config.js <file>` for details.',
  updateCommand: 'npm run lint:naming:update',
});
