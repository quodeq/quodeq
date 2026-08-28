import { useEffect } from 'react';

/**
 * Lock the page's `.dashboard` ancestor to viewport height while the map is
 * mounted, restoring it on unmount.
 *
 * The one DOM-reaching concern of the map page, isolated here so the rest of
 * useMapPageState stays testable without a document. Uses
 * document.querySelector because the .dashboard ancestor is outside this
 * component's React tree; a ref-based approach would require threading a ref
 * from a distant parent.
 */
export function useDashboardFullHeight() {
  useEffect(() => {
    if (typeof document === 'undefined') return;
    const dashboard = document.querySelector('.dashboard');
    if (dashboard) {
      dashboard.classList.add('dashboard--fullheight');
      return () => dashboard.classList.remove('dashboard--fullheight');
    }
  }, []);
}
