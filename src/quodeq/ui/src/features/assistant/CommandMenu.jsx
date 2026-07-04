import React from 'react';

/**
 * Autocomplete popup for slash commands, anchored above the composer.
 * Pure presentation: selection/keyboard state lives in AssistantPane.
 */
export function CommandMenu({ suggestions, selectedIndex, onPick }) {
  if (!suggestions.length) return null;
  return (
    <div className="assistant-command-menu" role="listbox">
      {suggestions.map((cmd, i) => (
        <button
          type="button"
          key={cmd.name}
          role="option"
          aria-selected={i === selectedIndex}
          className={`assistant-command-item${i === selectedIndex ? ' selected' : ''}`}
          // mousedown (not click) so the textarea keeps focus
          onMouseDown={(event) => { event.preventDefault(); onPick(cmd); }}
        >
          <span className="assistant-command-name">/{cmd.name}</span>
          {cmd.argumentHint ? <span className="assistant-command-hint">{cmd.argumentHint}</span> : null}
          <span className="assistant-command-desc">{cmd.description}</span>
        </button>
      ))}
    </div>
  );
}
