import { useState, useEffect } from 'react';

/**
 * Manages a browser-history-backed navigation stack.
 *
 * Returns { navStack, activePage, navPush, navPop, navGoTo, navReset, navTab }.
 */
export function useNavStack() {
  const [navStack, setNavStack] = useState([{ page: 'overview' }]);

  // Initialize browser history state on mount
  useEffect(() => {
    window.history.replaceState({ navIndex: 0, entry: { page: 'overview' } }, '');
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Sync browser back/forward buttons with navStack
  useEffect(() => {
    function onPopState(e) {
      const targetIndex = e.state?.navIndex ?? 0;
      setNavStack((prev) => {
        if (targetIndex < prev.length - 1) {
          // Going back
          return prev.slice(0, targetIndex + 1);
        }
        if (targetIndex >= prev.length && e.state?.entry) {
          // Going forward — restore entry from history state
          return [...prev.slice(0, targetIndex), e.state.entry];
        }
        return prev;
      });
    }
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  function navPush(entry) {
    setNavStack((prev) => {
      const next = [...prev, entry];
      window.history.pushState({ navIndex: next.length - 1, entry }, '');
      return next;
    });
  }

  function navPop() {
    window.history.back(); // popstate handler updates navStack
  }

  function navGoTo(index) {
    const steps = navStack.length - 1 - index;
    if (steps > 0) window.history.go(-steps); // popstate handler updates navStack
  }

  function navReset() {
    setNavStack((prev) => {
      const stepsBack = prev.length - 1;
      if (stepsBack > 0) window.history.go(-stepsBack);
      return [{ page: 'overview' }];
    });
  }

  function navTab(page) {
    setNavStack((prev) => {
      const stepsBack = prev.length - 1;
      if (stepsBack > 0) window.history.go(-stepsBack);
      return [{ page }];
    });
  }

  const activePage = navStack[navStack.length - 1];

  // Scroll to top on every navigation
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [activePage]);

  return { navStack, activePage, navPush, navPop, navGoTo, navReset, navTab };
}
