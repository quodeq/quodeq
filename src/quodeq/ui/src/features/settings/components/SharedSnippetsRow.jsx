import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { sharedKeys } from '../../../api/queryKeys.js';
import { t } from '../../../strings/index.js';
import { SettingsOnOffPills, SettingsRowLabel } from './settingsRowParts.jsx';

/**
 * Whether a publish to the connected shared repository carries code snippets.
 * Off by default: without it findings are published with their location and
 * reason but not the code. Shows the pending choice while the save is in
 * flight, then whatever the status reports. Hidden while no repository is
 * connected or its URL is being changed.
 */
export default function SharedSnippetsRow({ status, hidden }) {
  if (hidden) return null;
  return <SnippetsChoice withSnippets={status?.withSnippets} />;
}

function SnippetsChoice({ withSnippets }) {
  const { setSharedSnippets } = useApi();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (enabled) => setSharedSnippets(enabled),
    onError: (err) => console.warn('[SharedSnippetsRow] saving the snippets choice failed:', err),
    onSettled: () => queryClient.invalidateQueries({ queryKey: sharedKeys.status() }),
  });
  const on = mutation.isPending ? mutation.variables : Boolean(withSnippets);
  return (
    <div className="settings-row">
      <SettingsRowLabel hintSlot={false} label={t('settings.sharedSnippets')} description={t('settings.sharedSnippetsDesc')} />
      <SettingsOnOffPills on={on} onToggle={(value) => mutation.mutate(value)} />
    </div>
  );
}
