import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

const state = {
  provider: 'claude', model: 'sonnet',
  messages: [
    { role: 'user', text: 'why grade C?' },
    { role: 'tool', name: 'get_scores' },
    { role: 'assistant', text: '**Security** is graded C.' },
    { role: 'action', actionId: 'a1', actionType: 'create_standard', summary: { id: 'x', name: 'X', principleCount: 1 } },
    { role: 'local', text: '**Commands** listed' },
    { role: 'tool', name: 'get_report', argsSummary: '{"dimension":"security"}' },
  ],
  streaming: false, error: null, sendMessage: vi.fn(),
  catalog: null, addLocalExchange: vi.fn(), resetConversation: vi.fn(),
};
vi.mock('./AssistantDrawerProvider.jsx', () => ({ useAssistantDrawer: () => state }));
vi.mock('./ActionPreviewCard.jsx', () => ({ ActionPreviewCard: ({ action }) => <div>card:{action.actionId}</div> }));
import { AssistantPane } from './AssistantDrawer.jsx';

it('renders messages, markdown, tool marker, and action card', () => {
  render(<AssistantPane uiState={{ activeTab: 'overview' }} />);
  expect(screen.getByText('why grade C?')).toBeInTheDocument();
  expect(screen.getByText(/used get_scores/i)).toBeInTheDocument();
  expect(screen.getByText('Security').tagName).toBe('STRONG'); // markdown rendered
  expect(screen.getByText('card:a1')).toBeInTheDocument();
  expect(screen.getByText('Commands').tagName).toBe('STRONG'); // local renders markdown
  expect(screen.getByText(/get_report · \{"dimension":"security"\}/)).toBeInTheDocument();
});

it('renders the prompt input', () => {
  render(<AssistantPane uiState={{}} />);
  expect(screen.getByPlaceholderText(/ask/i)).toBeInTheDocument();
});

it('Enter sends the message with uiState', () => {
  render(<AssistantPane uiState={{ activeTab: 'standards' }} />);
  const input = screen.getByPlaceholderText(/ask/i);
  fireEvent.change(input, { target: { value: 'make a standard' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(state.sendMessage).toHaveBeenCalledWith('make a standard', { activeTab: 'standards' });
});
