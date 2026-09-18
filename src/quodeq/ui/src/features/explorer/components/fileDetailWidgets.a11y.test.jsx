import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { GroupHeader } from './fileDetailWidgets.jsx';

describe('GroupHeader heading semantics', () => {
  it('exposes the title as a level-3 heading', () => {
    render(<GroupHeader title="Critical" count={5} />);
    expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('Critical');
  });
});
