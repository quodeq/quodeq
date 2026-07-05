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
    const next = [...navStackRef.current, entry];
    setNavStack(next);
    history.pushState({ navIndex: next.length - 1, entry }, '');
  }

  function navPop() {
    history.back();
  }

  function navGoTo(index) {
    const steps = navStackRef.current.length - 1 - index;
    if (steps > 0) history.go(-steps);
  }

  function navReset() {
    const stepsBack = navStackRef.current.length - 1;
    setNavStack([{ page: DEFAULT_PAGE }]);
    if (stepsBack > 0) history.go(-stepsBack);
  }

  function navTab(page, params = {}) {
    const prev = navStackRef.current;
    const stepsBack = prev.length - 1;
    const prevKey = prev.length === 1 && prev[0].page === page ? (prev[0]._tabKey || 0) : 0;
    const next = [{ page, _tabKey: prevKey + 1, ...params }];
    setNavStack(next);
    if (stepsBack > 0) history.go(-stepsBack);
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
    // The window itself doesn't scroll — the dashboard <main> does.
    // Reset its scrollTop so navigating to a new screen always lands
    // at the top instead of inheriting the previous screen's offset.
    const main = document.querySelector('.app-shell__main-column > .dashboard');
    if (main) main.scrollTop = 0;
    else window.scrollTo({ top: 0 });
  }, [activePage]);

  return { navStack, activePage, navPush, navPop, navGoTo, navReset, navTab };
}
