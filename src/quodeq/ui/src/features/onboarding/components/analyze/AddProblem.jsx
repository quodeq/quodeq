import { t } from '../../../../strings/index.js';
import AccessPanel from '../../../github-access/components/AccessPanel.jsx';
import { Detail } from '../../../github-access/components/AccessGuidance.jsx';

function ErrorRow({ error }) {
  return (
    <div className="analyze-clone__error" role="alert">
      <p className="analyze-clone__message">{error.message}</p>
      <Detail detail={error.detail} />
      <button type="button" className="term-btn term-btn--secondary" onClick={error.retry}>{t('onboarding.retry')}</button>
    </div>
  );
}

/**
 * What stopped an add before it was handed over: the access panel when the
 * url cannot be reached, or the error row (with `retry`) when the
 * registration or the clone start was refused. Renders nothing otherwise;
 * a clone that started is followed by the Repositories tab's tile, not here.
 *
 * @param {{ add: ReturnType<import('../../hooks/useAnalyzeLaunch.js').useAnalyzeLaunch>, url: string }} props
 */
export default function AddProblem({ add, url }) {
  if (add.accessFailure) {
    return <AccessPanel failure={add.accessFailure} url={url} onResolved={add.run} onRetry={add.run} />;
  }
  if (add.startError) return <ErrorRow error={add.startError} />;
  return null;
}
