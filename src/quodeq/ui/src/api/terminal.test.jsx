import { it, expect } from 'vitest';
import { terminalSocketUrl } from './terminal.js';

it('derives a ws:// url from the current origin', () => {
  const url = terminalSocketUrl({ href: 'http://localhost:7863/', protocol: 'http:' });
  expect(url).toBe('ws://localhost:7863/api/terminal/ws');
});
it('upgrades to wss on https', () => {
  const url = terminalSocketUrl({ href: 'https://host:9/', protocol: 'https:' });
  expect(url.startsWith('wss://host:9/')).toBe(true);
});
it('appends the session id as a query param when given', () => {
  const url = terminalSocketUrl({ href: 'http://localhost:7863/', protocol: 'http:' }, 'abc123');
  expect(url).toBe('ws://localhost:7863/api/terminal/ws?session=abc123');
});
it('omits the session param when not given (back-compat default session)', () => {
  const url = terminalSocketUrl({ href: 'http://localhost:7863/', protocol: 'http:' });
  expect(url.includes('session')).toBe(false);
});
