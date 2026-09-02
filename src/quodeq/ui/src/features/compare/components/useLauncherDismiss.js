import { useEffect } from 'react';

/**
 * Dismiss mechanics shared by the duel and dimension launcher popovers: a
 * press anywhere outside, Escape, or any OUTSIDE scroll/resize (which moves
 * the fixed-position anchor) closes the menu. The menu's own list scrolls
 * too (capture sees those events as well), and scrolling the options must
 * not dismiss them.
 */
export function useLauncherDismiss(open, btnRef, menuRef, close) {
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => {
      if (!btnRef.current?.contains(e.target) && !menuRef.current?.contains(e.target)) close();
    };
    const onEsc = (e) => { if (e.key === 'Escape') close(); };
    const onAnchorMoved = (e) => {
      if (menuRef.current && e.target instanceof Node && menuRef.current.contains(e.target)) return;
      close();
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onEsc);
    window.addEventListener('scroll', onAnchorMoved, true);
    window.addEventListener('resize', onAnchorMoved);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onEsc);
      window.removeEventListener('scroll', onAnchorMoved, true);
      window.removeEventListener('resize', onAnchorMoved);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
}
