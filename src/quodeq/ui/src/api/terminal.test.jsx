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
