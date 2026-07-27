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

it('shows skills as suggestion cards and no slash-command list (the composer "/" menu covers that)', () => {
  render(<AssistantWelcome catalog={catalog} view="overview" onPick={() => {}} />);
  expect(screen.queryByText('/help')).toBeNull();
  expect(screen.queryByText('/clear')).toBeNull();
  expect(screen.queryByText('/explain-score')).toBeNull(); // skills are cards, not text
  expect(screen.getByRole('button', { name: 'Explain score' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Create standard' })).toBeInTheDocument();
});

it('pill click pre-fills, does not send', () => {
  const onPick = vi.fn();
  render(<AssistantWelcome catalog={catalog} view="overview" onPick={onPick} />);
  fireEvent.click(screen.getByRole('button', { name: 'Explain score' }));
  expect(onPick).toHaveBeenCalledWith('/explain-score ');
});

it('renders without a catalog (fetch failed): intro only, no cards', () => {
  const { container } = render(<AssistantWelcome catalog={null} view="overview" onPick={() => {}} />);
  expect(screen.getByText(/explain scores/i)).toBeInTheDocument();
  expect(container.querySelector('.assistant-suggest-card')).toBeNull();
  expect(screen.queryByText('Suggested')).toBeNull();
});

const RO_CATALOG = { skills: [
  { name: 'explain-score', description: 'd', views: ['overview'], requiresWrite: false },
  { name: 'verify-finding', description: 'd', views: ['violations'], requiresWrite: true },
  { name: 'create-standard', description: 'd', views: ['standards'], requiresWrite: true },
] };

it('read-only mode hides write-shaped pills and drops the draft-standards line', () => {
  render(<AssistantWelcome catalog={RO_CATALOG} view="violations" onPick={() => {}} readOnly />);
  expect(screen.queryByRole('button', { name: /verify finding/i })).toBeNull();
  expect(screen.queryByRole('button', { name: /create standard/i })).toBeNull();
  expect(screen.getByRole('button', { name: /explain score/i })).toBeInTheDocument();
  expect(screen.getByText(/dig into findings for this remote project/i)).toBeInTheDocument();
  expect(screen.queryByText(/draft standards/i)).toBeNull();
});

it('default mode keeps every pill and the standard intro', () => {
  render(<AssistantWelcome catalog={RO_CATALOG} view="violations" onPick={() => {}} />);
  expect(screen.getByRole('button', { name: /verify finding/i })).toBeInTheDocument();
  expect(screen.getByText(/draft standards for this project/i)).toBeInTheDocument();
});
