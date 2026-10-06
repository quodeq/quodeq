import { useId } from 'react';
import { TermHeader } from '../../../../components/terminal/index.js';
import { t } from '../../../../strings/index.js';
import WelcomePaths from '../WelcomePaths.jsx';
import '../../../../styles/onboarding-welcome.css';

// The three things quodeq does, in order; `num` is the mono row marker.
// Built per render so the string catalog is read at render time.
function howRows() {
  return [
    { num: '01', label: t('onboarding.how1Label'), text: t('onboarding.how1') },
    { num: '02', label: t('onboarding.how2Label'), text: t('onboarding.how2') },
    { num: '03', label: t('onboarding.how3Label'), text: t('onboarding.how3') },
  ];
}

function HowItWorks() {
  const titleId = useId();
  return (
    <section className="onboarding-how" aria-labelledby={titleId}>
      <TermHeader name={t('onboarding.termWelcome')} />
      <h2 id={titleId} className="onboarding-how__title">{t('onboarding.howTitle')}</h2>
      <ol className="onboarding-how__list">
        {howRows().map((row) => (
          <li key={row.num} className="onboarding-how__row">
            <span className="onboarding-how__num" aria-hidden="true">{row.num}</span>
            <span className="onboarding-how__body">
              <span className="onboarding-how__label">{row.label}</span>
              <span className="onboarding-how__text">{row.text}</span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

/**
 * The welcome panel: how quodeq works on the left (scan, review, score), the
 * three ways in on the right (WelcomePaths). `adaptation` says what already
 * exists: a connected evaluations repository and its host, local projects,
 * and whether Settings opened it (then there is no "skip for now").
 */
export default function WelcomeStep({ onStart, onConnect, onDisconnect, onImport, onSkip, adaptation }) {
  const pathsTitleId = useId();
  const fromSettings = Boolean(adaptation?.fromSettings);
  return (
    <div className="onboarding-step onboarding-step--welcome onboarding-welcome--split">
      <HowItWorks />
      <section className="onboarding-paths" aria-labelledby={pathsTitleId}>
        <h2 id={pathsTitleId} className="onboarding-paths__title">{t('onboarding.startWith')}</h2>
        <WelcomePaths
          onStart={onStart}
          onConnect={onConnect}
          onDisconnect={onDisconnect}
          onImport={onImport}
          adaptation={adaptation}
        />
        {!fromSettings && (
          <footer className="onboarding-welcome__footer">
            <button type="button" className="term-btn term-btn--ghost" onClick={onSkip}>{t('onboarding.skipForNow')}</button>
          </footer>
        )}
      </section>
    </div>
  );
}
