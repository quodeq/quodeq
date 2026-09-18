import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { TopBarProgressHairline } from './TopBarRunChip.jsx';

describe('TopBarProgressHairline textual progress equivalent', () => {
  it('exposes progress as a progressbar with a numeric value', () => {
    render(<TopBarProgressHairline evaluating runProgress={{ percent: 42 }} />);
    const bar = screen.getByRole('progressbar');
    expect(bar).toHaveAttribute('aria-valuenow', '42');
    expect(bar).toHaveAttribute('aria-valuemin', '0');
    expect(bar).toHaveAttribute('aria-valuemax', '100');
  });
});
