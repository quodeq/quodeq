import { describe, it, expect } from 'vitest';
import { mergeMessages } from './AssistantDrawerProvider.jsx';

describe('mergeMessages', () => {
  it('interleaves two user turns with two assistant replies in send/arrival order', () => {
    const userTurns = [
      { role: 'user', text: 'q1', atIndex: 0 },
      { role: 'user', text: 'q2', atIndex: 1 },
    ];
    const streamMessages = [
      { role: 'assistant', text: 'a1' },
      { role: 'assistant', text: 'a2' },
    ];
    const merged = mergeMessages(userTurns, streamMessages);
    expect(merged.map((m) => [m.role, m.text])).toEqual([
      ['user', 'q1'],
      ['assistant', 'a1'],
      ['user', 'q2'],
      ['assistant', 'a2'],
    ]);
  });

  it('keeps two same-anchor user turns in send order before any stream message', () => {
    const userTurns = [
      { role: 'user', text: 'q1', atIndex: 0 },
      { role: 'user', text: 'q2', atIndex: 0 },
    ];
    // No reply yet: both users appear, in send order.
    expect(mergeMessages(userTurns, []).map((m) => [m.role, m.text])).toEqual([
      ['user', 'q1'],
      ['user', 'q2'],
    ]);
    // First reply arrives: both users still precede it.
    expect(
      mergeMessages(userTurns, [{ role: 'assistant', text: 'a1' }]).map((m) => [m.role, m.text]),
    ).toEqual([
      ['user', 'q1'],
      ['user', 'q2'],
      ['assistant', 'a1'],
    ]);
  });
});
