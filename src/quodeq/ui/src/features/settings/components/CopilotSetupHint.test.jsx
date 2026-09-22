import { afterAll, beforeAll, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import CopilotSetupHint from './CopilotSetupHint.jsx';

let stylesheet;

beforeAll(() => {
  stylesheet = document.createElement('style');
  const directory = dirname(fileURLToPath(import.meta.url));
  stylesheet.textContent = readFileSync(resolve(directory, '../../../styles/base.css'), 'utf8');
  document.head.append(stylesheet);
});

afterAll(() => stylesheet.remove());

it('fits the settings row without extra margins and wraps long commands', () => {
  const { container } = render(<CopilotSetupHint />);
  const hint = container.querySelector('.settings-install-hint');
  const style = getComputedStyle(hint);
  expect(style.alignSelf).toBe('stretch');
  expect(parseFloat(style.marginLeft)).toBe(0);
  expect(parseFloat(style.marginRight)).toBe(0);
  expect(parseFloat(style.minWidth)).toBe(0);
  expect(style.overflowWrap).toBe('anywhere');
});
