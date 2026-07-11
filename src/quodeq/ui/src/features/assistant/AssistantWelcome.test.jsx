import React from 'react';
import { it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { AssistantWelcome } from './AssistantWelcome.jsx';

const catalog = {
  skills: [
    { name: 'explain-score', description: 'Explain a dimension score', argumentHint: '[dimension]', views: ['overview'] },
    { name: 'create-standard', description: 'Draft a custom standard', argumentHint: '', views: ['standards'] },
  ],
  actions: [],
};

it('lists meta commands as text, skills as pills only', () => {
  render(<AssistantWelcome catalog={catalog} view="overview" onPick={() => {}} />);
  expect(screen.getByText('/help')).toBeInTheDocument();
  expect(screen.getByText('/clear')).toBeInTheDocument();
  expect(screen.queryByText('/actions')).toBeNull(); // hidden meta stays out
  expect(screen.queryByText('/explain-score')).toBeNull(); // skills are pills, not text
  expect(screen.getByRole('button', { name: 'Explain score' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Create standard' })).toBeInTheDocument();
});

it('pill click pre-fills, does not send', () => {
  const onPick = vi.fn();
  render(<AssistantWelcome catalog={catalog} view="overview" onPick={onPick} />);
  fireEvent.click(screen.getByRole('button', { name: 'Explain score' }));
  expect(onPick).toHaveBeenCalledWith('/explain-score ');
});

it('renders without a catalog (fetch failed)', () => {
  render(<AssistantWelcome catalog={null} view="overview" onPick={() => {}} />);
  expect(screen.getByText('/help')).toBeInTheDocument();
  expect(screen.queryByRole('button')).toBeNull(); // no pills without catalog
});
