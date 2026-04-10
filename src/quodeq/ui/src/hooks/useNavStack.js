import { useState, useEffect, useRef } from 'react';

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

function createNavActions(setNavStack, navStackRef) {
  function navPush(entry) {
    setNavStack((prev) => {
      const next = [...prev, entry];
      window.history.pushState({ navIndex: next.length - 1, entry }, '');
      return next;
    });
  }

  function navPop() {
    window.history.back();
  }

  function navGoTo(index) {
    const steps = navStackRef.current.length - 1 - index;
    if (steps > 0) window.history.go(-steps);
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
      const prevKey = prev.length === 1 && prev[0].page === page ? (prev[0]._tabKey || 0) : 0;
      return [{ page, _tabKey: prevKey + 1 }];
    });
  }

  return { navPush, navPop, navGoTo, navReset, navTab };
}

export function useNavStack() {
  const [navStack, setNavStack] = useState([{ page: 'overview' }]);
  const navStackRef = useRef(navStack);
  navStackRef.current = navStack;

  useEffect(() => {
    window.history.replaceState({ navIndex: 0, entry: { page: 'overview' } }, '');
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const handler = (e) => handlePopState(e, setNavStack);
    window.addEventListener('popstate', handler);
    return () => window.removeEventListener('popstate', handler);
  }, []);

  const { navPush, navPop, navGoTo, navReset, navTab } = createNavActions(setNavStack, navStackRef);
  const activePage = navStack[navStack.length - 1];

  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [activePage]);

  return { navStack, activePage, navPush, navPop, navGoTo, navReset, navTab };
}
