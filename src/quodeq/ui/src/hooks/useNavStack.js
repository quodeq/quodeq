import { useState, useEffect, useRef } from 'react';

const DEFAULT_PAGE = 'overview';

/** Default history adapter delegating to window.history. */
const defaultHistoryAdapter = {
  pushState: (...args) => window.history.pushState(...args),
  replaceState: (...args) => window.history.replaceState(...args),
  back: () => window.history.back(),
  go: (n) => window.history.go(n),
};

/**
 * Manages a browser-history-backed navigation stack.
 *
 * Returns { navStack, activePage, navPush, navPop, navGoTo, navReset, navTab }.
 */
function handlePopState(e, setNavStack) {
  const targetIndex = e.state?.navIndex ?? 0;
  setNavStack((prev) => {
    if (targetIndex < prev.length - 1) {
      return prev.slice(0, targetIndex + 1);
    }
    if (targetIndex >= prev.length && e.state?.entry) {
      return [...prev.slice(0, targetIndex), e.state.entry];
    }
    return prev;
  });
}

function createNavActions(setNavStack, navStackRef, history) {
  function navPush(entry) {
    setNavStack((prev) => {
      const next = [...prev, entry];
      history.pushState({ navIndex: next.length - 1, entry }, '');
      return next;
    });
  }

  function navPop() {
    history.back();
  }

  function navGoTo(index) {
    const steps = navStackRef.current.length - 1 - index;
    if (steps > 0) history.go(-steps);
  }

  function navReset() {
    setNavStack((prev) => {
      const stepsBack = prev.length - 1;
      if (stepsBack > 0) history.go(-stepsBack);
      return [{ page: DEFAULT_PAGE }];
    });
  }

  function navTab(page) {
    setNavStack((prev) => {
      const stepsBack = prev.length - 1;
      if (stepsBack > 0) history.go(-stepsBack);
      const prevKey = prev.length === 1 && prev[0].page === page ? (prev[0]._tabKey || 0) : 0;
      return [{ page, _tabKey: prevKey + 1 }];
    });
  }

  return { navPush, navPop, navGoTo, navReset, navTab };
}

export function useNavStack({ historyAdapter } = {}) {
  const history = historyAdapter || defaultHistoryAdapter;
  const [navStack, setNavStack] = useState([{ page: DEFAULT_PAGE }]);
  const navStackRef = useRef(navStack);
  navStackRef.current = navStack;

  useEffect(() => {
    history.replaceState({ navIndex: 0, entry: { page: DEFAULT_PAGE } }, '');
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const handler = (e) => handlePopState(e, setNavStack);
    window.addEventListener('popstate', handler);
    return () => window.removeEventListener('popstate', handler);
  }, []);

  const { navPush, navPop, navGoTo, navReset, navTab } = createNavActions(setNavStack, navStackRef, history);
  const activePage = navStack[navStack.length - 1];

  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [activePage]);

  return { navStack, activePage, navPush, navPop, navGoTo, navReset, navTab };
}
