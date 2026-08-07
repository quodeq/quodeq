import React from 'react';
import { pillsForView } from './commands.js';
import { QMarkIcon } from '../../components/QMarkIcon.jsx';
import { t } from '../../strings/index.js';

// Dot tints cycle so neighboring cards read as distinct entry points.
const DOT_TONES = ['info', 'accent', 'warning', 'success'];

/**
 * Empty-transcript state of the assistant pane: an intro row, skill
 * suggestions as tappable cards (view-relevant first), and the meta-command
 * menu. Clicking anything pre-fills the composer, never sends. Pure UI,
 * never persisted, never sent to the model; reappears on every fresh
 * session.
 */
export function AssistantWelcome({ catalog, view, onPick, readOnly = false }) {
  const pills = pillsForView(catalog, view, { readOnly });
  return (
    <div className="assistant-welcome">
      <div className="assistant-welcome-hero">
        <span className="assistant-compass-block" aria-hidden="true">
          <QMarkIcon className="assistant-compass" />
        </span>
        <p className="assistant-welcome-intro">
          {readOnly
            ? t('assistant.welcomeRemote')
            : t('assistant.welcomeLocal')}
          {' '}{t('assistant.welcomeHint')}
        </p>
      </div>
      {pills.length > 0 && (
        <div className="assistant-welcome-section">
          <div className="assistant-welcome-label">{t('assistant.suggested')}</div>
          <div className="assistant-suggest-grid">
            {pills.map((p, i) => (
              <button
                key={p.fill}
                type="button"
                className="assistant-suggest-card"
                aria-label={p.label}
                title={p.description}
                onClick={() => onPick(p.fill)}
              >
                <span className={`assistant-suggest-dot assistant-suggest-dot--${DOT_TONES[i % DOT_TONES.length]}`} aria-hidden="true" />
                <span className="assistant-suggest-text">
                  <span className="assistant-suggest-title">{p.label}</span>
                  {p.description && <span className="assistant-suggest-desc">{p.description}</span>}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
      {/* No slash-command list here: typing "/" in the composer opens the
          live CommandMenu autocomplete, which is the same catalog searchable. */}
    </div>
  );
}
