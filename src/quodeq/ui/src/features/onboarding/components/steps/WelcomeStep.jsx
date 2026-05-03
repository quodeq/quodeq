// Inline SVGs follow the project's monoline icon style:
// 24x24 viewBox, currentColor stroke, 2px width, round caps/joins.
const IconRepo = (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <line x1="6" y1="3" x2="6" y2="15" />
    <circle cx="18" cy="6" r="3" />
    <circle cx="6" cy="18" r="3" />
    <path d="M18 9a9 9 0 0 1-9 9" />
  </svg>
);

const IconAi = (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="4" y="4" width="16" height="16" rx="2" />
    <rect x="9" y="9" width="6" height="6" />
    <line x1="9" y1="2" x2="9" y2="4" />
    <line x1="15" y1="2" x2="15" y2="4" />
    <line x1="9" y1="20" x2="9" y2="22" />
    <line x1="15" y1="20" x2="15" y2="22" />
    <line x1="20" y1="9" x2="22" y2="9" />
    <line x1="20" y1="15" x2="22" y2="15" />
    <line x1="2" y1="9" x2="4" y2="9" />
    <line x1="2" y1="15" x2="4" y2="15" />
  </svg>
);

const IconStandard = (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="9" />
    <circle cx="12" cy="12" r="5" />
    <circle cx="12" cy="12" r="1.5" fill="currentColor" />
  </svg>
);

export default function WelcomeStep({ onStart, onSkip }) {
  const previews = [
    { icon: IconRepo, label: 'Connect a repository', sub: 'Git URL or local folder' },
    { icon: IconAi, label: 'Pick an AI provider', sub: 'Local CLI, Ollama, or cloud' },
    { icon: IconStandard, label: 'Pick a standard', sub: 'Start with one — run more later' },
  ];
  return (
    <div className="onboarding-step onboarding-step--welcome">
      <h1 className="onboarding-welcome__title">Welcome to <span className="onboarding-welcome__title-accent">quodeq</span></h1>
      <ul className="onboarding-welcome__preview">
        {previews.map((p, i) => (
          <li key={i}>
            <span className="onboarding-welcome__icon">{p.icon}</span>
            <span className="onboarding-welcome__row-text">
              <span className="onboarding-welcome__row-label">{p.label}</span>
              <span className="onboarding-welcome__row-sub">{p.sub}</span>
            </span>
          </li>
        ))}
      </ul>
      <div className="onboarding-welcome__actions">
        <button type="button" className="btn-primary" onClick={onStart}>Get started</button>
        <button type="button" className="btn-secondary" onClick={onSkip}>Maybe later</button>
      </div>
    </div>
  );
}
