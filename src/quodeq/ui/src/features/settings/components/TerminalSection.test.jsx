import { it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import TerminalSection from './TerminalSection.jsx';

beforeEach(() => localStorage.clear());

it('toggles the terminal on and off', () => {
  render(<TerminalSection />);
  const on = screen.getByRole('tab', { name: 'On' });
  fireEvent.click(on);
  expect(localStorage.getItem('cc-terminal-enabled')).toBe('true');
});
