import { useEffect } from 'react';

/** Dismiss any open breadcrumb menu (ellipsis or sibling) on an outside
 * press or Escape. */
export function useBreadcrumbDismiss(openKey, setOpenKey, rootRef) {
  useEffect(() => {
    if (openKey == null) return undefined;
    const onDown = (e) => { if (!rootRef.current?.contains(e.target)) setOpenKey(null); };
    const onEsc = (e) => { if (e.key === 'Escape') setOpenKey(null); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onEsc);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onEsc);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openKey]);
}
