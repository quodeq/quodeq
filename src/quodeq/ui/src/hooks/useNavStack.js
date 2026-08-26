import { useState, useEffect, useRef, useTransition } from 'react';

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
 * Returns { navStack, activePage, navPush, navPop, navReplace, navGoTo, navSwapAt, navReset, navTab }.
 */
function isScalar(v) {
  return v == null || typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean';
}

/**
 * History state carries only scalars (and arrays of scalars, e.g.
 * preselectDims); object payloads stay in React state and `entriesByIndex`.
 * pushState structured-clones its argument synchronously on the main thread,
 * and entries like evalprinciple/file carry a run's whole findings graph —
 * cloning that inside the click handler froze navigation for seconds before
 * React could even schedule a render (and risks the browser's history-state
 * size cap, which would abort the handler mid-click).
 */
function toHistoryEntry(entry) {
  const light = {};
  for (const [k, v] of Object.entries(entry)) {
    if (isScalar(v) || (Array.isArray(v) && v.every(isScalar))) light[k] = v;
  }
  return light;
}

function handlePopState(e, setNavStack, entriesByIndex) {
  const targetIndex = e.state?.navIndex ?? 0;
  setNavStack((prev) => {
    if (targetIndex < prev.length - 1) {
      return prev.slice(0, targetIndex + 1);
    }
    if (targetIndex >= prev.length && e.state?.entry) {
      // Forward: the full entry (with its object payload) lives in
      // entriesByIndex; the history-state copy is the scalar-only fallback
      // for entries pushed before a reload.
      const entry = entriesByIndex.get(targetIndex) || e.state.entry;
      return [...prev.slice(0, targetIndex), entry];
    }
    return prev;
  });
}

function createNavActions(setNavStack, navStackRef, history, entriesByIndex, startNavTransition) {
  function rememberEntry(index, entry) {
    entriesByIndex.set(index, entry);
    // pushState/swap truncated the browser's forward history — entries past
    // this index are unreachable now.
    for (const k of [...entriesByIndex.keys()]) {
      if (k > index) entriesByIndex.delete(k);
    }
  }

  function navPush(entry) {
    const next = [...navStackRef.current, entry];
    // Transition, not a plain set: a detail page can take hundreds of ms to
    // render (pretext layout effects per card, and the WebKit webview is
    // slower at it than Chromium), and a blocking render freezes the page
    // with the click seemingly ignored. In a transition React time-slices
    // the incoming page while the current one stays interactive, and the
    // exposed navPending drives a visible progress bar — the user feedback
    // a synchronous render can never paint.
    startNavTransition(() => {
      setNavStack(next);
    });
    rememberEntry(next.length - 1, entry);
    history.pushState({ navIndex: next.length - 1, entry: toHistoryEntry(entry) }, '');
  }

  function navPop() {
    history.back();
  }

  function replaceTop(entry, setStack) {
    // Swap the top entry in place: browser history must NOT grow, or Back has
    // to unwind every flip. Same purity rule as navPush (#363): state +
    // history as two sequential statements, never inside the updater.
    const prev = navStackRef.current;
    const next = [...prev.slice(0, -1), entry];
    setStack(next);
    entriesByIndex.set(next.length - 1, entry);
    history.replaceState({ navIndex: next.length - 1, entry: toHistoryEntry(entry) }, '');
  }

  function navReplace(entry) {
    // In-place view-state changes on the SAME screen (repositories tab flips,
    // typed filters). Plain set, never a transition: this state can be driven
    // by controlled inputs, and rendering keystrokes at transition priority
    // makes typing lag.
    replaceTop(entry, setNavStack);
  }

  function navGoTo(index) {
    const steps = navStackRef.current.length - 1 - index;
    if (steps > 0) history.go(-steps);
  }

  function navSwapAt(index, entry) {
    // Lateral move within one level of the path (the breadcrumb's sibling
    // menus): replace the entry at `index` and drop everything deeper.
    // Same shape as navTab: truncate state synchronously, then walk browser
    // history back — the resulting popstate finds the stack already cut and
    // no-ops (see handlePopState).
    const prev = navStackRef.current;
    const stepsBack = prev.length - 1 - index;
    if (stepsBack <= 0) {
      // Swapping the top entry (the common breadcrumb case: switching
      // dimension while ON the dimension page) is a real navigation to a
      // possibly-heavy page — transition it, unlike navReplace's view-state
      // flips.
      replaceTop(entry, (next) => startNavTransition(() => setNavStack(next)));
      return;
    }
    // Same transition rationale as navPush: sibling swaps land on the same
    // heavy pages (a big dimension from the breadcrumb's jump bar).
    startNavTransition(() => {
      setNavStack([...prev.slice(0, index), entry]);
    });
    rememberEntry(index, entry);
    history.go(-stepsBack);
  }

  function navReset() {
    const stepsBack = navStackRef.current.length - 1;
    // Overview on a large project renders heavy too; same transition.
    startNavTransition(() => {
      setNavStack([{ page: DEFAULT_PAGE }]);
    });
    rememberEntry(0, { page: DEFAULT_PAGE });
    if (stepsBack > 0) history.go(-stepsBack);
  }

  function navTab(page, params = {}) {
    const prev = navStackRef.current;
    const stepsBack = prev.length - 1;
    const prevKey = prev.length === 1 && prev[0].page === page ? (prev[0]._tabKey || 0) : 0;
    // Spread params first so page/_tabKey stay authoritative and can't be
    // clobbered by a caller-supplied params key.
    const entry = { ...params, page, _tabKey: prevKey + 1 };
    // Same transition rationale as navPush: tab targets (Violations on a
    // large project, the keyed tab-fade remount) render heavy too.
    startNavTransition(() => {
      setNavStack([entry]);
    });
    rememberEntry(0, entry);
    if (stepsBack > 0) history.go(-stepsBack);
  }

  return { navPush, navPop, navReplace, navGoTo, navSwapAt, navReset, navTab };
}

export function useNavStack({ historyAdapter } = {}) {
  const history = historyAdapter || defaultHistoryAdapter;
  const [navStack, setNavStack] = useState([{ page: DEFAULT_PAGE }]);
  const navStackRef = useRef(navStack);
  navStackRef.current = navStack;
  // Full entries (object payloads included) by stack index, for forward
  // restores — see toHistoryEntry for why history state can't hold them.
  const entriesByIndexRef = useRef(new Map([[0, { page: DEFAULT_PAGE }]]));
  // navPending is true while a navigation's target page is still rendering
  // in a transition — the caller's cue to show progress feedback.
  const [navPending, startNavTransition] = useTransition();

  useEffect(() => {
    history.replaceState({ navIndex: 0, entry: { page: DEFAULT_PAGE } }, '');
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    // Back/forward render the same heavy pages a push does; same transition.
    const handler = (e) => startNavTransition(() => {
      handlePopState(e, setNavStack, entriesByIndexRef.current);
    });
    window.addEventListener('popstate', handler);
    return () => window.removeEventListener('popstate', handler);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const { navPush, navPop, navReplace, navGoTo, navSwapAt, navReset, navTab } = createNavActions(setNavStack, navStackRef, history, entriesByIndexRef.current, startNavTransition);
  const activePage = navStack[navStack.length - 1];

  useEffect(() => {
    // The window itself doesn't scroll — the dashboard <main> does.
    // Reset its scrollTop so navigating to a new screen always lands
    // at the top instead of inheriting the previous screen's offset.
    const main = document.querySelector('.app-shell__main-column > .dashboard');
    if (main) main.scrollTop = 0;
    else window.scrollTo({ top: 0 });
  }, [activePage]);

  return { navStack, activePage, navPending, navPush, navPop, navReplace, navGoTo, navSwapAt, navReset, navTab };
}
