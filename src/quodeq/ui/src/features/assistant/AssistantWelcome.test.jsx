import React from 'react';
import { it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { AssistantWelcome } from './AssistantWelcome.jsx';

const catalog = {
  skills: [
    { name: 'explain-score', description: 'Explain a dimension score', argumentHint: '[dimension]', views: ['overview'] },
  ],
  actions: [],
};

it('lists meta commands and skills', () => {
  render(<AssistantWelcome catalog={catalog} view="overview" onPick={() => {}} />);
  expect(screen.getByText('/help')).toBeInTheDocument();
  expect(screen.getByText('/clear')).toBeInTheDocument();
  expect(screen.getByText('/explain-score')).toBeInTheDocument();
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
