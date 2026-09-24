// Providers where the web toggle does something. The set lives in
// vocab/provider.js next to the backend mirror it derives from; re-exported
// here for the importers of this module and features/settings/components/providerUtils.js.
import { WEB_TOOL_PROVIDERS } from '../vocab/provider.js';

export { WEB_TOOL_PROVIDERS };

export function providerSupportsWebTools(providerId) {
  return WEB_TOOL_PROVIDERS.has(providerId);
}
