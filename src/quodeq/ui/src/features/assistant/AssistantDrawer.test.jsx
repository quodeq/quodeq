import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
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
  streaming: false, error: null, sendMessage: vi.fn(), stopTurn: vi.fn(),
  catalog: null, addLocalExchange: vi.fn(), resetConversation: vi.fn(), readOnly: false,
};
vi.mock('./AssistantDrawerProvider.jsx', () => ({ useAssistantDrawer: () => state }));
vi.mock('./ActionPreviewCard.jsx', () => ({ ActionPreviewCard: ({ action }) => <div>card:{action.actionId}</div> }));
import { AssistantPane } from './AssistantDrawer.jsx';

beforeEach(() => {
  state.sendMessage.mockClear();
  state.stopTurn.mockClear();
  state.addLocalExchange.mockClear();
  state.resetConversation.mockClear();
});

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

it('focuses the prompt input when the pane is the active tab (so you can type without clicking)', () => {
  render(<AssistantPane uiState={{}} active />);
  expect(screen.getByPlaceholderText(/ask/i)).toHaveFocus();
});

it('does not focus the prompt input when the pane is a backgrounded tab', () => {
  render(<AssistantPane uiState={{}} active={false} />);
  expect(screen.getByPlaceholderText(/ask/i)).not.toHaveFocus();
});

it('Enter sends the message with uiState', () => {
  render(<AssistantPane uiState={{ activeTab: 'standards' }} />);
  const input = screen.getByPlaceholderText(/ask/i);
  fireEvent.change(input, { target: { value: 'make a standard' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(state.sendMessage).toHaveBeenCalledWith('make a standard', { activeTab: 'standards' });
});

it('answers /help locally and never posts it', () => {
  render(<AssistantPane uiState={{}} />);
  const input = screen.getByPlaceholderText(/ask/i);
  fireEvent.change(input, { target: { value: '/help' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(state.addLocalExchange).toHaveBeenCalledWith('/help', expect.stringContaining('/skills'));
  expect(state.sendMessage).not.toHaveBeenCalled();
});

it('/clear resets the conversation', () => {
  render(<AssistantPane uiState={{}} />);
  const input = screen.getByPlaceholderText(/ask/i);
  fireEvent.change(input, { target: { value: '/clear' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(state.resetConversation).toHaveBeenCalled();
  expect(state.sendMessage).not.toHaveBeenCalled();
});

it('shows the command menu while typing a slash prefix and fills on Tab', () => {
  render(<AssistantPane uiState={{}} />);
  const input = screen.getByPlaceholderText(/ask/i);
  fireEvent.change(input, { target: { value: '/he' } });
  expect(screen.getByRole('listbox')).toBeInTheDocument();
  fireEvent.keyDown(input, { key: 'Tab' });
  expect(input.value).toBe('/help ');
  expect(state.sendMessage).not.toHaveBeenCalled();
});

it('slash-prefixed skill names still go to the server', () => {
  render(<AssistantPane uiState={{ view: 'overview' }} />);
  const input = screen.getByPlaceholderText(/ask/i);
  fireEvent.change(input, { target: { value: '/explain-score security' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(state.sendMessage).toHaveBeenCalledWith('/explain-score security', { view: 'overview' });
});

it('shows the welcome panel when the transcript is empty', () => {
  const prev = state.messages;
  state.messages = [];
  render(<AssistantPane uiState={{ view: 'overview' }} />);
  expect(screen.getByText(/explain scores/i)).toBeInTheDocument();
  state.messages = prev;
});

it('shows a Stop control while a turn is streaming and it stops the turn', () => {
  state.streaming = true;
  render(<AssistantPane uiState={{}} />);
  fireEvent.click(screen.getByRole('button', { name: /stop/i }));
  expect(state.stopTurn).toHaveBeenCalled();
  state.streaming = false;
});

it('hides the Stop control when no turn is running', () => {
  render(<AssistantPane uiState={{}} />);
  expect(screen.queryByRole('button', { name: /stop/i })).toBeNull();
});

describe('read-only sessions (source: shared)', () => {
  const writeCatalog = {
    commands: [],
    skills: [
      { name: 'explain-score', description: 'Explain a dimension score', argumentHint: '' },
      { name: 'verify-finding', description: 'Verify a finding', argumentHint: '', requiresWrite: true },
      { name: 'create-standard', description: 'Draft a custom standard', argumentHint: '', requiresWrite: true },
    ],
    actions: [],
  };
  const prevCatalog = state.catalog;

  beforeEach(() => { state.catalog = writeCatalog; state.readOnly = true; });
  afterEach(() => { state.catalog = prevCatalog; state.readOnly = false; });

  it('autocomplete hides requiresWrite skills', () => {
    render(<AssistantPane uiState={{}} />);
    const input = screen.getByPlaceholderText(/ask/i);
    fireEvent.change(input, { target: { value: '/' } });
    expect(screen.getByText('/explain-score')).toBeInTheDocument();
    expect(screen.queryByText('/verify-finding')).toBeNull();
    expect(screen.queryByText('/create-standard')).toBeNull();
  });

  it('/skills hides requiresWrite skills and /help uses the read-only line', () => {
    render(<AssistantPane uiState={{}} />);
    const input = screen.getByPlaceholderText(/ask/i);
    fireEvent.change(input, { target: { value: '/skills' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    let response = state.addLocalExchange.mock.calls.at(-1)[1];
    expect(response).toContain('/explain-score');
    expect(response).not.toContain('/verify-finding');
    expect(response).not.toContain('/create-standard');

    fireEvent.change(input, { target: { value: '/help' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    response = state.addLocalExchange.mock.calls.at(-1)[1];
    expect(response).toContain('I can explain scores and dig into findings for this remote project.');
    expect(response).not.toContain('draft standards');
  });
});

describe('default (non-read-only) sessions', () => {
  it('autocomplete still offers write-shaped skills', () => {
    const prevCatalog = state.catalog;
    state.catalog = {
      commands: [],
      skills: [{ name: 'create-standard', description: 'Draft a custom standard', argumentHint: '', requiresWrite: true }],
      actions: [],
    };
    render(<AssistantPane uiState={{}} />);
    const input = screen.getByPlaceholderText(/ask/i);
    fireEvent.change(input, { target: { value: '/' } });
    expect(screen.getByText('/create-standard')).toBeInTheDocument();
    state.catalog = prevCatalog;
  });

  it('/help keeps the default "draft standards" line', () => {
    render(<AssistantPane uiState={{}} />);
    const input = screen.getByPlaceholderText(/ask/i);
    fireEvent.change(input, { target: { value: '/help' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    const response = state.addLocalExchange.mock.calls.at(-1)[1];
    expect(response).toContain('I can explain scores, dig into findings, and draft standards for this project.');
  });
});
