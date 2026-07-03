import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

const state = {
  isOpen: true, provider: 'claude', model: 'sonnet', height: 320,
  messages: [
    { role: 'user', text: 'why grade C?' },
    { role: 'tool', name: 'get_scores' },
    { role: 'assistant', text: '**Security** is graded C.' },
    { role: 'action', actionId: 'a1', actionType: 'create_standard', summary: { id: 'x', name: 'X', principleCount: 1 } },
  ],
  streaming: false, error: null, close: vi.fn(), setHeight: vi.fn(), sendMessage: vi.fn(),
};
vi.mock('./AssistantDrawerProvider.jsx', () => ({ useAssistantDrawer: () => state }));
vi.mock('./ActionPreviewCard.jsx', () => ({ ActionPreviewCard: ({ action }) => <div>card:{action.actionId}</div> }));
import { AssistantDrawer } from './AssistantDrawer.jsx';

it('renders messages, markdown, tool marker, and action card', () => {
  render(<AssistantDrawer uiState={{ activeTab: 'overview' }} />);
  expect(screen.getByText('why grade C?')).toBeInTheDocument();
  expect(screen.getByText(/used get_scores/i)).toBeInTheDocument();
  expect(screen.getByText('Security').tagName).toBe('STRONG'); // markdown rendered
  expect(screen.getByText('card:a1')).toBeInTheDocument();
});

it('Enter sends the message with uiState', () => {
  render(<AssistantDrawer uiState={{ activeTab: 'standards' }} />);
  const input = screen.getByPlaceholderText(/ask/i);
  fireEvent.change(input, { target: { value: 'make a standard' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(state.sendMessage).toHaveBeenCalledWith('make a standard', { activeTab: 'standards' });
});

it('renders nothing when closed', () => {
  state.isOpen = false;
  const { container } = render(<AssistantDrawer uiState={{}} />);
  expect(container.firstChild).toBeNull();
  state.isOpen = true;
});
