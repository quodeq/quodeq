import { useState } from 'react';
import { useProviderDetection } from './useProviderDetection.js';
import { readActiveProviderState } from './useActiveProviderState.js';
import { providerLabel, serverProviderId } from '../providerLabels.js';

/**
 * Who reviews the code: the provider configured in Settings (id and model
 * set) when there is one, else the best one detected on this machine. The
 * drawer embeds the Settings provider tabs; closing it reads the configured
 * provider back, the way the old provider step's continue did.
 *
 * `selection` is the wizard's provider ({ id, model, classification } under
 * the server's id, or null while none is known); `timeLimitS` is the
 * configured provider's time limit (null when unset).
 *
 * @param {{ detect?: () => Promise<object[]> }} [deps]
 */
export function useReviewer({ detect } = {}) {
  const { status, preselection } = useProviderDetection({ detect });
  const [active, setActive] = useState(readActiveProviderState);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const configured = Boolean(active.id && active.model);

  let selection = null;
  if (configured) selection = { id: active.id, model: active.model, classification: null };
  else if (preselection) {
    selection = { id: serverProviderId(preselection.id), model: preselection.model, classification: preselection.classification };
  }

  return {
    status,
    configured,
    label: providerLabel(selection?.id ?? null),
    model: selection?.model ?? null,
    selection,
    timeLimitS: configured ? active.timeLimitS : null,
    drawerOpen,
    openDrawer: () => setDrawerOpen(true),
    closeDrawer: () => {
      setActive(readActiveProviderState());
      setDrawerOpen(false);
    },
  };
}
