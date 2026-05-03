export default function WelcomeStep({ onStart, onSkip }) {
  return (
    <div className="onboarding-step onboarding-step--welcome">
      <h1 className="onboarding-welcome__title">Welcome to quodeq</h1>
      <p className="onboarding-welcome__pitch">
        Audit code quality against the standards you care about. Let's set up your first project — takes about two minutes.
      </p>
      <ul className="onboarding-welcome__preview">
        <li><span aria-hidden="true">🔗</span> Connect repo</li>
        <li><span aria-hidden="true">🤖</span> Pick AI provider</li>
        <li><span aria-hidden="true">📐</span> Pick a standard</li>
      </ul>
      <div className="onboarding-welcome__actions">
        <button type="button" className="btn btn--primary" onClick={onStart}>Get started</button>
        <button type="button" className="btn btn--ghost" onClick={onSkip}>Maybe later</button>
      </div>
    </div>
  );
}
