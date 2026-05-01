import React from 'react';
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { violationFixPlanSpec } from './violationFixPlanSpec.jsx';

describe('violationFixPlanSpec', () => {
  it('returns null for missing violation', () => {
    expect(violationFixPlanSpec(null)).toBeNull();
    expect(violationFixPlanSpec(undefined)).toBeNull();
  });

  it('builds a spec with id, title, copy, download, and render', () => {
    const v = {
      severity: 'critical',
      principle: 'SRP',
      dimension: 'maintainability',
      file: 'src/foo.js',
      line: 12,
      title: 'God object',
      reason: 'Class does too much',
    };
    const spec = violationFixPlanSpec(v);
    expect(spec).not.toBeNull();
    expect(spec.id).toMatch(/^fixplan:violation:/);
    expect(spec.type).toBe('fixplan-violation');
    expect(spec.title).toMatch(/fix plan/i);
    expect(typeof spec.copy).toBe('function');
    expect(typeof spec.download).toBe('function');
    const dl = spec.download();
    expect(dl.filename).toMatch(/\.md$/);
    expect(dl.body).toEqual(spec.copy());
  });

  it('uses titleOverride when provided', () => {
    const spec = violationFixPlanSpec({ principle: 'SRP', dimension: 'maintainability' }, 'Custom title');
    expect(spec.title).toMatch(/^Custom title/);
  });

  it('renders ReportContent with markdown body', () => {
    const spec = violationFixPlanSpec({ principle: 'SRP', file: 'a.js', title: 'x' });
    const { container } = render(<>{spec.render()}</>);
    expect(container.querySelector('.side-pane-md')).not.toBeNull();
  });
});
