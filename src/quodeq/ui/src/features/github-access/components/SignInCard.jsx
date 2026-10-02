import { useEffect, useRef } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { openExternal as defaultOpenExternal } from '../../updates/openExternal.js';
import { t } from '../../../strings/index.js';
import { useDeviceFlow } from '../hooks/useDeviceFlow.js';
import { FLOW_PHASE } from '../accessVocab.js';

const ENDED_PHASES = [FLOW_PHASE.DONE, FLOW_PHASE.EXPIRED, FLOW_PHASE.DENIED, FLOW_PHASE.ERROR];

function CodeBlock({ userCode, verificationUri, openExternal }) {
  return (
    <div className="access-card__code-block">
      <p className="access-card__hint">{t('githubAccess.enterCode')}</p>
      <code className="access-card__code" aria-label={t('githubAccess.enterCode')}>{userCode}</code>
      <div className="onboarding-step__actions">
        <button type="button" className="term-btn term-btn--secondary" onClick={() => navigator.clipboard?.writeText(userCode)}>{t('githubAccess.copyCode')}</button>
        <button type="button" className="term-btn term-btn--secondary" onClick={() => openExternal(verificationUri)}>{t('githubAccess.openGithub')}</button>
      </div>
      <p className="access-card__waiting">{t('githubAccess.waiting')}</p>
    </div>
  );
}

function Terminal({ phase, login, error, onStartAgain }) {
  if (phase === FLOW_PHASE.DONE) return <p className="access-card__ok">{t('githubAccess.signedInAs', { login })}</p>;
  const text = phase === FLOW_PHASE.EXPIRED ? t('githubAccess.expired')
    : phase === FLOW_PHASE.DENIED ? t('githubAccess.denied') : error;
  return (
    <div>
      <p className="inline-error" role="alert">{text}</p>
      <button type="button" className="term-btn term-btn--secondary" onClick={onStartAgain}>{t('githubAccess.startAgain')}</button>
    </div>
  );
}

/** Primary rung: the GitHub device flow, inline. */
export default function SignInCard({ onSignedIn, pollMs, openExternal = defaultOpenExternal }) {
  const { startDeviceFlow, getDeviceFlow } = useApi();
  const flow = useDeviceFlow({ startDeviceFlow, getDeviceFlow, onSignedIn, pollMs });
  const openedRef = useRef(false);

  useEffect(() => {
    if (flow.phase === FLOW_PHASE.AWAITING_USER) {
      if (!openedRef.current) {
        openedRef.current = true;
        openExternal(flow.verificationUri);
      }
    } else {
      openedRef.current = false;
    }
  }, [flow.phase, flow.verificationUri, openExternal]);

  const starting = flow.phase === FLOW_PHASE.IDLE || flow.phase === FLOW_PHASE.STARTING;
  return (
    <section className="access-card access-card--primary">
      <h4 className="access-card__title">{t('githubAccess.signIn')}</h4>
      <p className="access-card__desc">{t('githubAccess.signInDesc')}</p>
      {starting && (
        <button type="button" className="term-btn term-btn--primary term-btn--filled" onClick={flow.begin} disabled={flow.phase === FLOW_PHASE.STARTING}>
          {t('githubAccess.signIn')}
        </button>
      )}
      {flow.phase === FLOW_PHASE.AWAITING_USER && <CodeBlock userCode={flow.userCode} verificationUri={flow.verificationUri} openExternal={openExternal} />}
      {ENDED_PHASES.includes(flow.phase) && (
        <Terminal phase={flow.phase} login={flow.login} error={flow.error} onStartAgain={flow.begin} />
      )}
    </section>
  );
}
