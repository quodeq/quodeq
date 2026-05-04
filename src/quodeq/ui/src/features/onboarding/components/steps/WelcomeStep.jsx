import { TermHeader } from '../../../../components/terminal/index.js';

const PREVIEW_ITEMS = [
  { label: 'connect a repository', sub: 'git url or local folder' },
  { label: 'pick an ai provider', sub: 'local cli, ollama, or cloud' },
  { label: 'pick a standard', sub: 'start with one — run more later' },
];

export default function WelcomeStep({ onStart, onSkip }) {
  return (
    <div className="onboarding-step onboarding-step--welcome">
      <TermHeader name="welcome" sub="pick a path" />
      <h1 className="onboarding-welcome__title">
        welcome to <span className="onboarding-welcome__title-accent">quodeq</span>
      </h1>
      <ul className="onboarding-welcome__preview">
        {PREVIEW_ITEMS.map((p) => (
          <li key={p.label}>
            <span className="onboarding-welcome__marker" aria-hidden="true">▸</span>
            <span className="onboarding-welcome__row-text">
              <span className="onboarding-welcome__row-label">{p.label}</span>
              <span className="onboarding-welcome__row-sub">{p.sub}</span>
            </span>
          </li>
        ))}
      </ul>
      <div className="onboarding-welcome__actions">
        <button type="button" className="term-btn--primary" onClick={onStart}>get started</button>
        <button type="button" className="term-btn--secondary" onClick={onSkip}>maybe later</button>
      </div>
    </div>
  );
}
