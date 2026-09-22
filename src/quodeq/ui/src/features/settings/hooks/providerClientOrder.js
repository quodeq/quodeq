/**
 * Ordering for the AI-client list.
 *
 * The provider tabs and the assistant's provider tabs both fetch the same
 * client list and show it in the order ai_providers.json declares, so the
 * sort lives here instead of in each hook.
 */

// Providers with no declared order sort after every declared one.
const DEFAULT_PROVIDER_ORDER = 50;

/**
 * Sort AI clients by their provider config's `order` field.
 *
 * @param {Array<{id: string}>} clients Raw client list from the API.
 * @param {Object} providerConfigs ai_providers.json contents, keyed by provider id.
 * @returns {Array<{id: string}>} A new sorted array; `clients` is not mutated.
 */
export function sortClientsByProviderOrder(clients, providerConfigs) {
  return [...clients].sort((a, b) => {
    const oa = providerConfigs?.[a.id]?.order ?? DEFAULT_PROVIDER_ORDER;
    const ob = providerConfigs?.[b.id]?.order ?? DEFAULT_PROVIDER_ORDER;
    return oa - ob;
  });
}
