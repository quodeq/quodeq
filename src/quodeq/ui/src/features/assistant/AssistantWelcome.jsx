import React from 'react';
import { VISIBLE_META_COMMANDS, pillsForView } from './commands.js';

/**
 * Empty-transcript state of the assistant pane: a one-line intro, the
 * meta-command list, and skill pills (view-relevant first). Skills appear
 * only as pills, never as text lines. Pure UI, never persisted, never sent
 * to the model; reappears on every fresh session.
 */
export function AssistantWelcome({ catalog, view, onPick }) {
  const pills = pillsForView(catalog, view);
  return (
    <div className="assistant-welcome">
      <p className="assistant-welcome-intro">
        I can explain scores, dig into findings, and draft standards for this project.
      </p>
      <ul className="assistant-welcome-commands">
        {VISIBLE_META_COMMANDS.map((c) => (
          <li key={c.name}><code>/{c.name}</code> {c.description}</li>
        ))}
      </ul>
      {pills.length > 0 && (
        <div className="assistant-welcome-pills">
          {pills.map((p) => (
            <button
              key={p.fill}
              type="button"
              className="assistant-pill"
              title={p.description}
              onClick={() => onPick(p.fill)}
            >
              {p.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
