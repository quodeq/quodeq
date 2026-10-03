import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { TopBarProgressHairline } from './TopBarRunChip.jsx';

const here = dirname(fileURLToPath(import.meta.url));

describe('top bar pending line', () => {
  it('sweeps while data is pending and no run is in flight', () => {
    const { container } = render(<TopBarProgressHairline pending evaluating={false} runProgress={null} />);
    const line = container.querySelector('.topbar-pending');
    expect(line).not.toBeNull();
    expect(container.querySelector('.topbar-progress')).toBeNull();
  });

  it('takes priority over run progress while pending', () => {
    const { container } = render(<TopBarProgressHairline pending evaluating runProgress={{ percent: 42 }} />);
    expect(container.querySelector('.topbar-pending')).not.toBeNull();
    expect(container.querySelector('.topbar-progress')).toBeNull();
  });

  it('hands back to run progress once settled', () => {
    const { container } = render(<TopBarProgressHairline pending={false} evaluating runProgress={{ percent: 42 }} />);
    expect(container.querySelector('.topbar-pending')).toBeNull();
    expect(container.querySelector('.topbar-progress')).not.toBeNull();
  });

  it('renders nothing when idle', () => {
    const { container } = render(<TopBarProgressHairline pending={false} evaluating={false} runProgress={null} />);
    expect(container.firstChild).toBeNull();
  });
});

describe('pending stylesheet', () => {
  const dashboardCss = readFileSync(resolve(here, '../styles/dashboard.css'), 'utf8');
  const terminalCss = readFileSync(resolve(here, '../styles/terminal.css'), 'utf8');

  it('sections no longer draw their own pending line', () => {
    expect(dashboardCss).not.toMatch(/\.section-pending::before/);
    expect(dashboardCss).not.toMatch(/\.nav-pending-bar\s*\{/);
  });

  it('sections still mute their text while pending', () => {
    expect(dashboardCss).toMatch(/\.section-pending\s*\{[^}]*--color-text:\s*var\(--color-text-muted\)/);
  });

  it('the top bar owns the one sweeping line', () => {
    expect(terminalCss).toMatch(/\.topbar-pending\s*\{/);
  });
});
