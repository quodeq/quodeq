import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import AppearanceSection from './AppearanceSection.jsx';

// #6680 - the mode pill group is a mutually-exclusive choice, so it needs
// radiogroup/radio semantics (aria-checked), not independent aria-pressed
// buttons.
describe('AppearanceSection mode pill group a11y', () => {
  const setup = (themeMode = 'system') => render(
    <AppearanceSection
      themeMode={themeMode}
      themeFamily="daruma"
      onApplyMode={vi.fn()}
      onApplyFamily={vi.fn()}
    />,
  );

  it('exposes the mode group as a labelled radiogroup', () => {
    setup();
    expect(screen.getByRole('radiogroup', { name: 'Appearance' })).toBeInTheDocument();
  });

  it('marks only the active mode as the checked radio', () => {
    setup('dark');
    const checked = screen.getByRole('radio', { checked: true });
    expect(checked).toHaveTextContent('Dark');
    expect(screen.getAllByRole('radio', { checked: false })).toHaveLength(2);
  });
});
