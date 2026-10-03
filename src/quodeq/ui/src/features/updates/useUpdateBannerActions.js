import { useApi } from '../../api/ApiContext.jsx';

/**
 * UpdateBanner's two write actions — the first-run disclosure receipt and
 * the dismiss click — sourced from useApi() instead of a direct api/index.js
 * import, so the banner can be tested without hitting fetch.
 */
export function useUpdateBannerActions() {
  const { markUpdateDisclosed, dismissUpdate } = useApi();
  return { markUpdateDisclosed, dismissUpdate };
}
