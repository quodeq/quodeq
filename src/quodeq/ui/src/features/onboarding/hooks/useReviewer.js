import { useState } from 'react';
import { useProviderDetection } from './useProviderDetection.js';
import { readActiveProviderState } from './useActiveProviderState.js';
import { providerLabel, serverProviderId } from '../providerLabels.js';
import { ACTIVE_PROVIDER_KEY, notifyProviderSettingsChanged } from '../../../constants.js';
import { writeString } from '../../../adapters/storage.js';

/**
 * Who reviews the code: the provider configured in Settings (id and model
 * set) when there is one, else the best one detected on this machine. The
 * drawer embeds the Settings provider tabs; closing it reads the configured
 * provider back, the way the old provider step's continue did.
 *
 * `selection` is the wizard's provider ({ id, model, classification } under
 * the server's id), set only once a model is known: the app requires one for
 * every provider. A detection without a model is still named (`detectedId`,
 * `label`) but not launchable; `chooseModel` makes it the active provider and
 * opens the drawer on its tab. `timeLimitS` is the configured provider's time
 * limit (null when unset).
 *
 * @param {{ detect?: () => Promise<object[]> }} [deps]
 */
export function useReviewer({ detect } = {}) {
  const { status, preselection } = useProviderDetection({ detect });
  const [active, setActive] = useState(readActiveProviderState);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const configured = Boolean(active.id && active.model);
  const detectedId = !configured && preselection ? serverProviderId(preselection.id) : null;

  let selection = null;
  if (configured) selection = { id: active.id, model: active.model, classification: null };
  else if (detectedId && preselection.model) {
    selection = { id: detectedId, model: preselection.model, classification: preselection.classification };
  }

  return {
    status,
    configured,
    detectedId,
    label: providerLabel(selection?.id ?? detectedId),
    model: selection?.model ?? null,
    selection,
    timeLimitS: configured ? active.timeLimitS : null,
    drawerOpen,
    openDrawer: () => setDrawerOpen(true),
    // The provider tabs open on the persisted active provider: point it at
    // the detected one, the way picking its tab would.
    chooseModel: () => {
      if (detectedId) {
        writeString(ACTIVE_PROVIDER_KEY, detectedId);
        notifyProviderSettingsChanged();
      }
      setDrawerOpen(true);
    },
    closeDrawer: () => {
      setActive(readActiveProviderState());
      setDrawerOpen(false);
    },
  };
}
