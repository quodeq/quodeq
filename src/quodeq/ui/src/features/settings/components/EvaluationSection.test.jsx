import { it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import EvaluationSection from './EvaluationSection.jsx';
import { NEW_FINDINGS_ONLY_KEY } from '../hooks/useLiveFeedSettings.js';

beforeEach(() => { localStorage.clear(); });

it('defaults to New only', () => {
  render(<EvaluationSection />);
  expect(screen.getByRole('tab', { name: 'New only' })).toHaveAttribute('aria-selected', 'true');
});

it('switching to All persists the opt-out', () => {
  render(<EvaluationSection />);
  fireEvent.click(screen.getByRole('tab', { name: 'All' }));
  expect(localStorage.getItem(NEW_FINDINGS_ONLY_KEY)).toBe('false');
  expect(screen.getByRole('tab', { name: 'All' })).toHaveAttribute('aria-selected', 'true');
});
