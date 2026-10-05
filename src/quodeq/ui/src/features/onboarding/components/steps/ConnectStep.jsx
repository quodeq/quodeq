import { useQueryClient } from '@tanstack/react-query';
import { TermHeader } from '../../../../components/terminal/index.js';
import { t } from '../../../../strings/index.js';
import { useApi } from '../../../../api/ApiContext.jsx';
import { sharedKeys } from '../../../../api/queryKeys.js';
import { useSharedActions } from '../../../dashboard/hooks/useSharedActions.js';
import { useFolderPicker } from '../../../dashboard/hooks/useFolderPicker.jsx';
import EvaluationsRepoForm from '../../../dashboard/components/EvaluationsRepoForm.jsx';

/**
 * Connect an evaluations repository, by git url or local folder. The PUT only
 * starts the connect job (202); once it has started the step hands over with
 * `onConnectStarted()` (the wizard closes onto the Repositories tab, where
 * the sync strip shows the download and a failure comes back in the card).
 * A start the server refuses (not a git repository, an access failure)
 * stays here, under the field.
 *
 * `onBack` returns to the welcome when the step was reached from it; opened
 * on its own (the Repositories header or strip) there is no welcome behind
 * it, so `onCancel` closes the wizard instead.
 */
export default function ConnectStep({ onBack, onCancel, onConnectStarted }) {
  const { connectShared } = useApi();
  const queryClient = useQueryClient();
  const { connecting, connectError, accessFailure, connect } = useSharedActions({ connectShared });
  const { browseFolder, picker } = useFolderPicker();

  const handleConnect = async (url) => {
    const started = await connect(url);
    if (!started) return;
    // The strip polls on its own; this shows the running job at once.
    queryClient.invalidateQueries({ queryKey: sharedKeys.status() });
    onConnectStarted?.();
  };

  // The way out sits at the left of the form's connect: back to the welcome
  // when it was reached from there, cancel when opened on its own.
  const secondaryAction = onBack
    ? <button type="button" className="term-btn term-btn--secondary" onClick={onBack}>{t('common.back')}</button>
    : <button type="button" className="term-btn term-btn--secondary" onClick={onCancel}>{t('onboarding.cancel')}</button>;
  return (
    <div className="onboarding-step onboarding-step--connect">
      <TermHeader name={t('onboarding.termConnect')} />
      <p className="onboarding-step__pitch">{t('onboarding.connectDesc')}</p>
      <EvaluationsRepoForm
        onConnect={handleConnect}
        connecting={connecting}
        error={connectError}
        accessFailure={accessFailure}
        browseFolder={browseFolder}
        secondaryAction={secondaryAction}
      />
      {picker}
    </div>
  );
}
