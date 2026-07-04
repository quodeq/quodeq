import React from 'react';
import { META_COMMANDS, pillsForView } from './commands.js';

/**
 * Empty-transcript state of the assistant pane: a one-line intro, the
 * command/skill catalog, and context-aware suggestion pills. Pure UI, never
 * persisted, never sent to the model; reappears on every fresh session.
 */
export function AssistantWelcome({ catalog, view, onPick }) {
  const pills = pillsForView(catalog, view);
  const skills = catalog?.skills ?? [];
  return (
    <div className="assistant-welcome">
      <p className="assistant-welcome-intro">
        I can explain scores, dig into findings, and draft standards for this project.
      </p>
      <ul className="assistant-welcome-commands">
        {META_COMMANDS.map((c) => (
          <li key={c.name}><code>/{c.name}</code> {c.description}</li>
        ))}
        {skills.map((s) => (
          <li key={s.name}><code>/{s.name}</code> {s.description}</li>
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
