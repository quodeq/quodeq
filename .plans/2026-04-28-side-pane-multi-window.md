# SidePane multi-window dock — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-report `ReportPane` with a generic `SidePane` dock that hosts up to 3 stacked windows. Reports are the first window type; future types (fix plans) plug in via the same `useRegisterWindowSpec` API.

**Architecture:** A new `SidePaneProvider` exposes a `windows` array (ordered top→bottom) with `addWindow`, `removeWindow`, `toggleWindow`, `hasWindow`, `closeAll`. Pages register a *spec* (`{id, type, title, render}`) via a hook; the topbar's per-type button toggles that spec into/out of the dock. The dock UI renders each window with its own header (title + per-window chrome + close X) and an independently scrollable body. A horizontal drag handle resizes adjacent windows. Cap = 3; over-cap button is rendered disabled.

**Tech Stack:** React 18, Vite, Vitest + @testing-library/react.

**Baseline:** This plan is built on top of `origin/feature/report-pane-divider` (the divider styling commit `e39481f0`). The 5 commits on `feature/report-pane-page-aware` are abandoned — the page-aware semantics are subsumed by the new register-by-id flow.

---

## File map

### Delete

- `src/quodeq/ui/src/features/report-viewer/ReportViewerProvider.jsx`
- `src/quodeq/ui/src/features/report-viewer/ReportViewerProvider.test.jsx`
- `src/quodeq/ui/src/features/report-viewer/ReportViewerContext.jsx`
- `src/quodeq/ui/src/features/report-viewer/ReportPane.jsx`
- `src/quodeq/ui/src/features/report-viewer/ReportPane.test.jsx`
- `src/quodeq/ui/src/features/report-viewer/ReportPane.css`
- `src/quodeq/ui/src/features/report-viewer/index.js`

### Keep / move

- `src/quodeq/ui/src/features/report-viewer/markdownRenderer.jsx` → move to `src/quodeq/ui/src/features/side-pane/reportContent.jsx` (it's specific to report bodies; lives with the new report window-content layer).
- `src/quodeq/ui/src/features/report-viewer/markdownRenderer.test.jsx` → move alongside.
- `src/quodeq/ui/src/features/report-viewer/resizeMath.{js,test.js}` → move to `src/quodeq/ui/src/features/side-pane/paneWidthMath.{js,test.js}` (rename to clarify scope).

### Create (new `src/quodeq/ui/src/features/side-pane/` directory)

- `SidePaneContext.jsx` — context + `useSidePane()` hook.
- `SidePaneProvider.jsx` — provider, windows array, mutations, paneWidth, Esc handler.
- `SidePaneProvider.test.jsx` — covers add/remove/toggle/hasWindow/closeAll/cap behavior + paneWidth persistence + Esc.
- `useRegisterWindowSpec.js` — consumer hook used by pages to register a spec for a given type.
- `useRegisterWindowSpec.test.jsx` — covers spec registration, button-state derivation, toggle wiring.
- `SidePane.jsx` — the rendered dock (the right-column container, draggable left gutter, vertical stack of windows with horizontal resizers between them).
- `SidePane.test.jsx` — covers renders nothing when empty, renders one/two/three windows, splitter resize, etc.
- `SidePane.css` — dock + window styling. Replaces `ReportPane.css`. Reuses the divider gutter rules from the divider-styling commit.
- `SidePaneWindow.jsx` — a single window inside the dock: header (title + copy + download + close X) + body. Renders `spec.render()`.
- `SidePaneWindow.test.jsx` — header buttons + body rendering.
- `index.js` — barrel exports `SidePaneProvider`, `useSidePane`, `useRegisterWindowSpec`, `SidePane`.

### Modify

- `src/quodeq/ui/src/App.jsx` — swap `ReportViewerProvider` → `SidePaneProvider`, swap `<ReportPane />` → `<SidePane />`, and any `useReportViewer` references.
- `src/quodeq/ui/src/components/TopBar.jsx` — replace the single Report button block with: per-type button (`Report` for now) wired to `useRegisterWindowSpec` data, plus a new `Close all` icon button that's only rendered when the dock has ≥1 window.
- `src/quodeq/ui/src/features/explorer/components/ExplorerPage.jsx` — call `useRegisterWindowSpec('report', spec)` instead of the old `setActiveBuilder`.
- `src/quodeq/ui/src/features/dashboard/components/AccumulatedOverviewPanel.jsx` — same migration.
- `src/quodeq/ui/src/styles/terminal.css` — already references `--report-pane-width`; rename to `--side-pane-width` everywhere it appears (lines 1353 and 1363, plus any others; grep before editing).

### CSS variable rename

`--report-pane-width` → `--side-pane-width`. Touches `terminal.css` and the new `SidePaneProvider.jsx` (which writes the value).

### localStorage key rename

Old: `quodeq.reportPaneWidth`. New: `quodeq.sidePaneWidth`. One-time migration: on provider mount, if the new key is unset and the old key exists, copy the value over and remove the old. (Implemented inline in `SidePaneProvider.jsx`'s `readStoredWidth`.)

---

## API shapes

### `SidePaneWindow` (the data type, not the React component — the React component is also called `SidePaneWindow`; there's no real ambiguity in JS but the data type is just a plain object literal)

```js
// A window spec — pages produce these; the provider stores them.
const spec = {
  id: 'report:overview:quodeq',  // stable per page+type; collisions = same window
  type: 'report',                 // discriminant; future: 'fix-plan' etc.
  title: 'Code Quality Report — quodeq',
  render: () => <ReportContent markdown={...} />,
  // Optional: per-window export hooks for the header chrome.
  copy: () => '...markdown...',  // returns string for clipboard
  download: () => ({ filename: '...', body: '...' }),  // returns blob bits
};
```

`copy` and `download` are the bits that used to live on the pane-level header. Now they're per-window so each window can copy/download its own content.

### Context API

```js
const ctx = useSidePane();
// ctx = {
//   windows,         // Array<spec>, ordered top→bottom
//   isOpen,          // boolean, derived: windows.length > 0
//   paneWidth,       // number (px)
//   setPaneWidth,    // (px) => void
//   addWindow,       // (spec) => void; respects MAX_WINDOWS cap (silent no-op if at cap)
//   removeWindow,    // (id) => void
//   toggleWindow,    // (spec) => void; if id present remove, else add (if under cap)
//   hasWindow,       // (id) => boolean
//   closeAll,        // () => void
//   MAX_WINDOWS,     // 3
// };
```

### Hook for pages

```js
useRegisterWindowSpec(type, spec)
// - type: string discriminant ('report')
// - spec: SidePaneWindow object, or null/undefined to register nothing
// - On mount: if spec is non-null, registers it with the provider under this type.
// - On unmount or spec.id change: unregisters the previous spec.
// - Does NOT add to the dock automatically — only the toolbar does that on click.
// - Returns an object: { spec, hasWindow, isAtCap, toggle } so the toolbar button
//   for this type can render its state purely from this hook.
```

The provider keeps a separate `Map<type, spec>` of *registered specs* (page-side state) in addition to `windows` (dock-side state). `useRegisterWindowSpec` writes to the registered-specs map; the toolbar reads from it.

---

## Tasks

### Task 1: Roll back the old branch and start fresh

**Files:**
- (Branch ops only.)

- [ ] **Step 1: Verify clean working tree.**

Run: `git status`
Expected: `nothing to commit, working tree clean`. If not, stop and ask.

- [ ] **Step 2: Create the implementation branch off the divider commit.**

Run:
```bash
git fetch origin feature/report-pane-divider
git checkout -b feature/side-pane-multi-window origin/feature/report-pane-divider
```

Confirm with: `git log --oneline -3`
Expected: `e39481f0 feat(report-pane): make divider clearly draggable` is the latest commit.

- [ ] **Step 3: No commit in this task — just branch setup.**

---

### Task 2: Move shared sub-modules into the new `side-pane/` directory

**Files:**
- Create: `src/quodeq/ui/src/features/side-pane/` (the directory)
- Move: `markdownRenderer.jsx` → `side-pane/reportContent.jsx`
- Move: `markdownRenderer.test.jsx` → `side-pane/reportContent.test.jsx`
- Move: `resizeMath.js` → `side-pane/paneWidthMath.js`
- Move: `resizeMath.test.js` → `side-pane/paneWidthMath.test.js`

- [ ] **Step 1: Create the directory and move files.**

```bash
mkdir -p src/quodeq/ui/src/features/side-pane
git mv src/quodeq/ui/src/features/report-viewer/markdownRenderer.jsx src/quodeq/ui/src/features/side-pane/reportContent.jsx
git mv src/quodeq/ui/src/features/report-viewer/markdownRenderer.test.jsx src/quodeq/ui/src/features/side-pane/reportContent.test.jsx
git mv src/quodeq/ui/src/features/report-viewer/resizeMath.js src/quodeq/ui/src/features/side-pane/paneWidthMath.js
git mv src/quodeq/ui/src/features/report-viewer/resizeMath.test.js src/quodeq/ui/src/features/side-pane/paneWidthMath.test.js
```

- [ ] **Step 2: Rename the exported symbols inside the moved files to match new names.**

In `src/quodeq/ui/src/features/side-pane/reportContent.jsx`: rename the exported `ReportMarkdown` component to `ReportContent`. Update references in the same file.

In `src/quodeq/ui/src/features/side-pane/reportContent.test.jsx`: update the import and any usages of `ReportMarkdown` to `ReportContent`. Test descriptions should reference "report content" instead of "markdown renderer" if they currently do — keep the test bodies intact otherwise.

In `src/quodeq/ui/src/features/side-pane/paneWidthMath.js`: rename the exported `clampPaneWidth` to `clampSidePaneWidth`.

In `src/quodeq/ui/src/features/side-pane/paneWidthMath.test.js`: update the import and any direct usages.

- [ ] **Step 3: Run only the moved tests to confirm they still pass.**

Run: `cd src/quodeq/ui && npx vitest run src/features/side-pane/`
Expected: existing tests in those two files PASS.

- [ ] **Step 4: Commit.**

```bash
git add src/quodeq/ui/src/features/side-pane src/quodeq/ui/src/features/report-viewer
git commit -m "refactor(side-pane): move shared report+resize utilities into new side-pane feature dir"
```

---

### Task 3: Create `SidePaneContext` and `SidePaneProvider` with windows-array model (TDD)

**Files:**
- Create: `src/quodeq/ui/src/features/side-pane/SidePaneContext.jsx`
- Create: `src/quodeq/ui/src/features/side-pane/SidePaneProvider.jsx`
- Create: `src/quodeq/ui/src/features/side-pane/SidePaneProvider.test.jsx`

- [ ] **Step 1: Write the failing test file.**

Create `src/quodeq/ui/src/features/side-pane/SidePaneProvider.test.jsx` with the following content:

```jsx
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { SidePaneProvider } from './SidePaneProvider.jsx';
import { useSidePane } from './SidePaneContext.jsx';

function spec(id, title = id) {
  return { id, type: 'report', title, render: () => <p>{`body:${id}`}</p> };
}

function Probe() {
  const { windows, isOpen, addWindow, removeWindow, toggleWindow, hasWindow, closeAll, MAX_WINDOWS } = useSidePane();
  return (
    <div>
      <div data-testid="state">{isOpen ? `open:${windows.map(w => w.id).join(',')}` : 'closed'}</div>
      <div data-testid="cap">{`cap:${MAX_WINDOWS}`}</div>
      <div data-testid="has-a">{hasWindow('a') ? 'yes' : 'no'}</div>
      <button onClick={() => addWindow(spec('a'))}>add-a</button>
      <button onClick={() => addWindow(spec('b'))}>add-b</button>
      <button onClick={() => addWindow(spec('c'))}>add-c</button>
      <button onClick={() => addWindow(spec('d'))}>add-d</button>
      <button onClick={() => removeWindow('a')}>remove-a</button>
      <button onClick={() => toggleWindow(spec('a'))}>toggle-a</button>
      <button onClick={closeAll}>close-all</button>
    </div>
  );
}

describe('SidePaneProvider', () => {
  it('starts closed with no windows and exposes MAX_WINDOWS=3', () => {
    render(<SidePaneProvider><Probe /></SidePaneProvider>);
    expect(screen.getByTestId('state')).toHaveTextContent('closed');
    expect(screen.getByTestId('cap')).toHaveTextContent('cap:3');
  });

  it('addWindow appends to the bottom of the stack and opens the pane', () => {
    render(<SidePaneProvider><Probe /></SidePaneProvider>);
    fireEvent.click(screen.getByText('add-a'));
    fireEvent.click(screen.getByText('add-b'));
    expect(screen.getByTestId('state')).toHaveTextContent('open:a,b');
  });

  it('removeWindow removes by id; pane closes when the last window goes', () => {
    render(<SidePaneProvider><Probe /></SidePaneProvider>);
    fireEvent.click(screen.getByText('add-a'));
    fireEvent.click(screen.getByText('add-b'));
    fireEvent.click(screen.getByText('remove-a'));
    expect(screen.getByTestId('state')).toHaveTextContent('open:b');
    fireEvent.click(screen.getByText('add-a'));
    fireEvent.click(screen.getByText('remove-a'));
    fireEvent.click(screen.getByText('remove-a'));
    // remove-a a second time is a no-op (already removed)
    expect(screen.getByTestId('state')).toHaveTextContent('open:b');
  });

  it('toggleWindow adds when absent and removes when present', () => {
    render(<SidePaneProvider><Probe /></SidePaneProvider>);
    fireEvent.click(screen.getByText('toggle-a'));
    expect(screen.getByTestId('state')).toHaveTextContent('open:a');
    fireEvent.click(screen.getByText('toggle-a'));
    expect(screen.getByTestId('state')).toHaveTextContent('closed');
  });

  it('addWindow is a no-op when already at MAX_WINDOWS=3', () => {
    render(<SidePaneProvider><Probe /></SidePaneProvider>);
    fireEvent.click(screen.getByText('add-a'));
    fireEvent.click(screen.getByText('add-b'));
    fireEvent.click(screen.getByText('add-c'));
    fireEvent.click(screen.getByText('add-d'));
    expect(screen.getByTestId('state')).toHaveTextContent('open:a,b,c');
  });

  it('hasWindow reflects current dock contents', () => {
    render(<SidePaneProvider><Probe /></SidePaneProvider>);
    expect(screen.getByTestId('has-a')).toHaveTextContent('no');
    fireEvent.click(screen.getByText('add-a'));
    expect(screen.getByTestId('has-a')).toHaveTextContent('yes');
    fireEvent.click(screen.getByText('remove-a'));
    expect(screen.getByTestId('has-a')).toHaveTextContent('no');
  });

  it('closeAll empties the dock', () => {
    render(<SidePaneProvider><Probe /></SidePaneProvider>);
    fireEvent.click(screen.getByText('add-a'));
    fireEvent.click(screen.getByText('add-b'));
    fireEvent.click(screen.getByText('close-all'));
    expect(screen.getByTestId('state')).toHaveTextContent('closed');
  });

  it('Escape closes all windows when the pane is open', () => {
    render(<SidePaneProvider><Probe /></SidePaneProvider>);
    fireEvent.click(screen.getByText('add-a'));
    act(() => { fireEvent.keyDown(window, { key: 'Escape' }); });
    expect(screen.getByTestId('state')).toHaveTextContent('closed');
  });

  it('useSidePane throws outside the provider', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<Probe />)).toThrow();
    spy.mockRestore();
  });

  it('writes --side-pane-width to the document root when open and 0px when closed', () => {
    function PaneWidthProbe() {
      const { addWindow, closeAll, paneWidth } = useSidePane();
      return (
        <div>
          <div data-testid="pw">{paneWidth}</div>
          <button onClick={() => addWindow(spec('x'))}>add-x</button>
          <button onClick={closeAll}>close-all</button>
        </div>
      );
    }
    render(<SidePaneProvider><PaneWidthProbe /></SidePaneProvider>);
    const initial = screen.getByTestId('pw').textContent;
    expect(Number(initial)).toBeGreaterThan(0);
    fireEvent.click(screen.getByText('add-x'));
    expect(document.documentElement.style.getPropertyValue('--side-pane-width')).toBe(`${initial}px`);
    fireEvent.click(screen.getByText('close-all'));
    expect(document.documentElement.style.getPropertyValue('--side-pane-width')).toBe('0px');
  });

  it('migrates the legacy quodeq.reportPaneWidth localStorage key on first mount', () => {
    localStorage.setItem('quodeq.reportPaneWidth', '777');
    localStorage.removeItem('quodeq.sidePaneWidth');
    function PWProbe() {
      const { paneWidth } = useSidePane();
      return <div data-testid="pw">{paneWidth}</div>;
    }
    render(<SidePaneProvider><PWProbe /></SidePaneProvider>);
    expect(screen.getByTestId('pw')).toHaveTextContent('777');
    expect(localStorage.getItem('quodeq.sidePaneWidth')).toBe('777');
    expect(localStorage.getItem('quodeq.reportPaneWidth')).toBeNull();
  });
});
```

- [ ] **Step 2: Run tests, expect them to fail (modules don't exist yet).**

Run: `cd src/quodeq/ui && npx vitest run src/features/side-pane/SidePaneProvider.test.jsx`
Expected: import errors for `SidePaneProvider` and `SidePaneContext`.

- [ ] **Step 3: Create `SidePaneContext.jsx`.**

```jsx
import { createContext, useContext } from 'react';

export const SidePaneContext = createContext(null);

export function useSidePane() {
  const ctx = useContext(SidePaneContext);
  if (ctx === null) {
    throw new Error('useSidePane must be used inside a <SidePaneProvider>');
  }
  return ctx;
}
```

- [ ] **Step 4: Create `SidePaneProvider.jsx`.**

```jsx
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { SidePaneContext } from './SidePaneContext.jsx';
import { clampSidePaneWidth } from './paneWidthMath.js';

const STORAGE_KEY = 'quodeq.sidePaneWidth';
const LEGACY_STORAGE_KEY = 'quodeq.reportPaneWidth';
const DEFAULT_WIDTH_PX = 560;
const MAX_WINDOWS = 3;

function readStoredWidth() {
  try {
    if (typeof localStorage === 'undefined') return DEFAULT_WIDTH_PX;
    let raw = localStorage.getItem(STORAGE_KEY);
    if (raw == null) {
      // One-time migration from the pre-rename key.
      const legacy = localStorage.getItem(LEGACY_STORAGE_KEY);
      if (legacy != null) {
        localStorage.setItem(STORAGE_KEY, legacy);
        localStorage.removeItem(LEGACY_STORAGE_KEY);
        raw = legacy;
      }
    }
    const n = raw ? parseInt(raw, 10) : NaN;
    return Number.isFinite(n) && n > 0 ? n : DEFAULT_WIDTH_PX;
  } catch {
    return DEFAULT_WIDTH_PX;
  }
}

function writeStoredWidth(px) {
  try {
    if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY, String(px));
  } catch {
    /* quota / disabled — ignore */
  }
}

export function SidePaneProvider({ children }) {
  const [windows, setWindows] = useState([]);
  const [paneWidth, setPaneWidthState] = useState(readStoredWidth);

  const isOpen = windows.length > 0;

  const hasWindow = useCallback(
    (id) => windows.some((w) => w.id === id),
    [windows],
  );

  const addWindow = useCallback((spec) => {
    if (!spec || !spec.id) return;
    setWindows((prev) => {
      if (prev.some((w) => w.id === spec.id)) return prev;
      if (prev.length >= MAX_WINDOWS) return prev;
      return [...prev, spec];
    });
  }, []);

  const removeWindow = useCallback((id) => {
    setWindows((prev) => prev.filter((w) => w.id !== id));
  }, []);

  const toggleWindow = useCallback((spec) => {
    if (!spec || !spec.id) return;
    setWindows((prev) => {
      if (prev.some((w) => w.id === spec.id)) {
        return prev.filter((w) => w.id !== spec.id);
      }
      if (prev.length >= MAX_WINDOWS) return prev;
      return [...prev, spec];
    });
  }, []);

  const closeAll = useCallback(() => setWindows([]), []);

  const setPaneWidth = useCallback((px) => {
    const next = clampSidePaneWidth(px, typeof window !== 'undefined' ? window.innerWidth : 1920);
    setPaneWidthState(next);
    writeStoredWidth(next);
  }, []);

  // Sync the open width into a CSS variable on the root so the grid template can read it.
  useEffect(() => {
    const root = document.documentElement;
    if (isOpen) {
      root.style.setProperty('--side-pane-width', `${paneWidth}px`);
    } else {
      root.style.setProperty('--side-pane-width', '0px');
    }
  }, [isOpen, paneWidth]);

  // Escape closes all windows when the pane is open.
  useEffect(() => {
    if (!isOpen) return undefined;
    function onKey(e) {
      if (e.key === 'Escape') {
        e.stopPropagation();
        setWindows([]);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen]);

  const value = useMemo(
    () => ({
      windows, isOpen, paneWidth,
      addWindow, removeWindow, toggleWindow, hasWindow, closeAll,
      setPaneWidth, MAX_WINDOWS,
    }),
    [windows, isOpen, paneWidth, addWindow, removeWindow, toggleWindow, hasWindow, closeAll, setPaneWidth],
  );

  return (
    <SidePaneContext.Provider value={value}>
      {children}
    </SidePaneContext.Provider>
  );
}
```

- [ ] **Step 5: Run tests, verify all pass.**

Run: `cd src/quodeq/ui && npx vitest run src/features/side-pane/SidePaneProvider.test.jsx`
Expected: 11 tests PASS.

- [ ] **Step 6: Commit.**

```bash
git add src/quodeq/ui/src/features/side-pane/SidePaneContext.jsx src/quodeq/ui/src/features/side-pane/SidePaneProvider.jsx src/quodeq/ui/src/features/side-pane/SidePaneProvider.test.jsx
git commit -m "feat(side-pane): provider with windows array, cap at 3, Esc-close, width persistence + legacy migration"
```

---

### Task 4: Create the `useRegisterWindowSpec` hook (TDD)

**Files:**
- Create: `src/quodeq/ui/src/features/side-pane/useRegisterWindowSpec.js`
- Create: `src/quodeq/ui/src/features/side-pane/useRegisterWindowSpec.test.jsx`

The hook lets a page declare "if my type is 'report', here's the spec to add when the user clicks the toolbar button." The provider tracks **registered specs** separately from **open windows**: a registered spec means "this type is available on this page"; an open window means "this spec is in the dock right now."

This requires extending the provider's context with a registered-specs map and the toolbar-facing helpers. We add those alongside the hook (small additions to the provider).

- [ ] **Step 1: Extend `SidePaneProvider.jsx` with the registered-specs map.**

Add the following to `SidePaneProvider.jsx`:

```jsx
// Inside the component:
const [registeredSpecs, setRegisteredSpecs] = useState({}); // { [type]: spec }

const registerSpec = useCallback((type, spec) => {
  setRegisteredSpecs((prev) => ({ ...prev, [type]: spec }));
}, []);

const unregisterSpec = useCallback((type) => {
  setRegisteredSpecs((prev) => {
    if (!(type in prev)) return prev;
    const next = { ...prev };
    delete next[type];
    return next;
  });
}, []);

const getRegisteredSpec = useCallback((type) => registeredSpecs[type] ?? null, [registeredSpecs]);
```

Add `registerSpec`, `unregisterSpec`, `getRegisteredSpec` to the context `value` and its `useMemo` deps.

- [ ] **Step 2: Write the failing test file.**

Create `src/quodeq/ui/src/features/side-pane/useRegisterWindowSpec.test.jsx`:

```jsx
import React, { useMemo } from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { SidePaneProvider } from './SidePaneProvider.jsx';
import { useSidePane } from './SidePaneContext.jsx';
import { useRegisterWindowSpec } from './useRegisterWindowSpec.js';

function Page({ id, title }) {
  const spec = useMemo(
    () => ({ id, type: 'report', title, render: () => <p>{`body:${id}`}</p> }),
    [id, title],
  );
  const { hasWindow, isAtCap, toggle } = useRegisterWindowSpec('report', spec);
  return (
    <div>
      <button data-testid="page-btn" onClick={toggle} disabled={isAtCap && !hasWindow}>
        {hasWindow ? 'remove' : isAtCap ? 'cap' : 'add'}
      </button>
    </div>
  );
}

function DockProbe() {
  const { windows } = useSidePane();
  return <div data-testid="dock">{windows.map((w) => w.id).join(',') || 'empty'}</div>;
}

describe('useRegisterWindowSpec', () => {
  it('toggling adds and removes the registered spec from the dock', () => {
    render(
      <SidePaneProvider>
        <Page id="p1" title="P1" />
        <DockProbe />
      </SidePaneProvider>,
    );
    expect(screen.getByTestId('dock')).toHaveTextContent('empty');
    fireEvent.click(screen.getByTestId('page-btn'));
    expect(screen.getByTestId('dock')).toHaveTextContent('p1');
    fireEvent.click(screen.getByTestId('page-btn'));
    expect(screen.getByTestId('dock')).toHaveTextContent('empty');
  });

  it('isAtCap is true when the dock holds MAX_WINDOWS distinct specs', () => {
    function Filler() {
      const { addWindow } = useSidePane();
      return (
        <button
          data-testid="fill"
          onClick={() => {
            addWindow({ id: 'x1', type: 'report', title: 'x1', render: () => null });
            addWindow({ id: 'x2', type: 'report', title: 'x2', render: () => null });
            addWindow({ id: 'x3', type: 'report', title: 'x3', render: () => null });
          }}
        >fill</button>
      );
    }
    render(
      <SidePaneProvider>
        <Filler />
        <Page id="p1" title="P1" />
      </SidePaneProvider>,
    );
    fireEvent.click(screen.getByTestId('fill'));
    // p1 is not in the dock and dock is at cap → button text reflects cap.
    expect(screen.getByTestId('page-btn')).toHaveTextContent('cap');
    expect(screen.getByTestId('page-btn')).toBeDisabled();
  });

  it('unmounting the page unregisters the spec but does not change the dock', () => {
    function Wrapper({ visible }) {
      return visible ? <Page id="p1" title="P1" /> : null;
    }
    function ToggleVisible() {
      const [v, setV] = React.useState(true);
      return (
        <>
          <button data-testid="hide" onClick={() => setV(false)}>hide</button>
          <Wrapper visible={v} />
        </>
      );
    }
    render(
      <SidePaneProvider>
        <ToggleVisible />
        <DockProbe />
      </SidePaneProvider>,
    );
    fireEvent.click(screen.getByTestId('page-btn'));
    expect(screen.getByTestId('dock')).toHaveTextContent('p1');
    act(() => { fireEvent.click(screen.getByTestId('hide')); });
    // Page is gone but its window persists in the dock — the spec is captured by reference.
    expect(screen.getByTestId('dock')).toHaveTextContent('p1');
  });

  it('passing a null spec leaves nothing registered (button hides via consumer logic)', () => {
    function NullPage() {
      const { hasWindow, isAtCap, toggle } = useRegisterWindowSpec('report', null);
      return (
        <button data-testid="null-btn" onClick={toggle} disabled>
          {hasWindow ? 'remove' : isAtCap ? 'cap' : 'add'}
        </button>
      );
    }
    render(
      <SidePaneProvider>
        <NullPage />
      </SidePaneProvider>,
    );
    expect(screen.getByTestId('null-btn')).toHaveTextContent('add');
    expect(screen.getByTestId('null-btn')).toBeDisabled();
    // Clicking does nothing (toggle is a no-op when spec is null)
    fireEvent.click(screen.getByTestId('null-btn'));
  });
});
```

- [ ] **Step 3: Run tests, expect them to fail.**

Run: `cd src/quodeq/ui && npx vitest run src/features/side-pane/useRegisterWindowSpec.test.jsx`
Expected: import error for `useRegisterWindowSpec`.

- [ ] **Step 4: Create `useRegisterWindowSpec.js`.**

```js
import { useEffect } from 'react';
import { useSidePane } from './SidePaneContext.jsx';

/**
 * Registers a window spec for a given type while the calling component is
 * mounted. The spec is *available* (the toolbar can add it on click) but is
 * not added to the dock until the user toggles it.
 *
 * Returns helpers the toolbar button uses to render its state.
 */
export function useRegisterWindowSpec(type, spec) {
  const ctx = useSidePane();
  const { registerSpec, unregisterSpec, hasWindow, toggleWindow, windows, MAX_WINDOWS } = ctx;

  useEffect(() => {
    if (!spec) {
      unregisterSpec(type);
      return undefined;
    }
    registerSpec(type, spec);
    return () => unregisterSpec(type);
  }, [type, spec, registerSpec, unregisterSpec]);

  const isInDock = spec ? hasWindow(spec.id) : false;
  const isAtCap = windows.length >= MAX_WINDOWS;

  return {
    spec: spec ?? null,
    hasWindow: isInDock,
    isAtCap,
    toggle: () => { if (spec) toggleWindow(spec); },
  };
}
```

- [ ] **Step 5: Run tests, verify all pass.**

Run: `cd src/quodeq/ui && npx vitest run src/features/side-pane/useRegisterWindowSpec.test.jsx`
Expected: 4 tests PASS.

Also re-run the provider tests to confirm the registerSpec/unregisterSpec additions didn't break anything:

Run: `cd src/quodeq/ui && npx vitest run src/features/side-pane/SidePaneProvider.test.jsx`
Expected: still 11 tests PASS.

- [ ] **Step 6: Commit.**

```bash
git add src/quodeq/ui/src/features/side-pane/SidePaneProvider.jsx src/quodeq/ui/src/features/side-pane/useRegisterWindowSpec.js src/quodeq/ui/src/features/side-pane/useRegisterWindowSpec.test.jsx
git commit -m "feat(side-pane): useRegisterWindowSpec hook + per-type spec registry"
```

---

### Task 5: Build the `SidePaneWindow` component (a single window inside the dock)

**Files:**
- Create: `src/quodeq/ui/src/features/side-pane/SidePaneWindow.jsx`
- Create: `src/quodeq/ui/src/features/side-pane/SidePaneWindow.test.jsx`

A window has its own header (title + optional copy/download buttons + close X) and an independently scrollable body.

- [ ] **Step 1: Write the failing test file.**

Create `src/quodeq/ui/src/features/side-pane/SidePaneWindow.test.jsx`:

```jsx
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { SidePaneWindow } from './SidePaneWindow.jsx';

beforeEach(() => {
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
});

function makeSpec(overrides = {}) {
  return {
    id: 'w1',
    type: 'report',
    title: 'My Window',
    render: () => <p>body content</p>,
    ...overrides,
  };
}

describe('SidePaneWindow', () => {
  it('renders the title and body', () => {
    const onClose = vi.fn();
    render(<SidePaneWindow spec={makeSpec()} onClose={onClose} />);
    expect(screen.getByText('My Window')).toBeInTheDocument();
    expect(screen.getByText('body content')).toBeInTheDocument();
  });

  it('Close button calls onClose with the window id', () => {
    const onClose = vi.fn();
    render(<SidePaneWindow spec={makeSpec({ id: 'abc' })} onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: /close window/i }));
    expect(onClose).toHaveBeenCalledWith('abc');
  });

  it('Copy button writes the result of spec.copy() to the clipboard', () => {
    render(<SidePaneWindow spec={makeSpec({ copy: () => 'clip!' })} onClose={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /copy/i }));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('clip!');
  });

  it('omits the Copy button when spec.copy is not provided', () => {
    render(<SidePaneWindow spec={makeSpec()} onClose={() => {}} />);
    expect(screen.queryByRole('button', { name: /copy/i })).toBeNull();
  });

  it('omits the Download button when spec.download is not provided', () => {
    render(<SidePaneWindow spec={makeSpec()} onClose={() => {}} />);
    expect(screen.queryByRole('button', { name: /download/i })).toBeNull();
  });

  it('Download button triggers spec.download() (smoke test only)', () => {
    const downloadFn = vi.fn(() => ({ filename: 'x.md', body: '# x' }));
    render(<SidePaneWindow spec={makeSpec({ download: downloadFn })} onClose={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /download/i }));
    expect(downloadFn).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run tests; expect them to fail.**

Run: `cd src/quodeq/ui && npx vitest run src/features/side-pane/SidePaneWindow.test.jsx`
Expected: import error for `SidePaneWindow`.

- [ ] **Step 3: Create `SidePaneWindow.jsx`.**

```jsx
import React, { useCallback, useEffect, useRef, useState } from 'react';

const COPY_FEEDBACK_MS = 1500;

function slugify(s) {
  return (s || 'window').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'window';
}

function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
}

function triggerDownload({ filename, body }) {
  const safeName = filename || `${slugify(body?.slice(0, 32))}-${todayISO()}.md`;
  const pyApi = typeof window !== 'undefined' && window.pywebview && window.pywebview.api;
  if (pyApi && typeof pyApi.save_file === 'function') {
    pyApi.save_file(body, safeName);
    return;
  }
  const blob = new Blob(['﻿', body], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = safeName; a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { a.remove(); URL.revokeObjectURL(url); }, 0);
}

export function SidePaneWindow({ spec, onClose }) {
  const bodyRef = useRef(null);
  const [justCopied, setJustCopied] = useState(false);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = 0;
  }, [spec.id]);

  useEffect(() => { setJustCopied(false); }, [spec.id]);

  useEffect(() => {
    if (!justCopied) return undefined;
    const t = setTimeout(() => setJustCopied(false), COPY_FEEDBACK_MS);
    return () => clearTimeout(t);
  }, [justCopied]);

  const onCopy = useCallback(() => {
    if (!spec.copy) return;
    navigator.clipboard?.writeText(spec.copy());
    setJustCopied(true);
  }, [spec]);

  const onDownload = useCallback(() => {
    if (!spec.download) return;
    triggerDownload(spec.download());
  }, [spec]);

  const onClickClose = useCallback(() => onClose(spec.id), [onClose, spec.id]);

  return (
    <section className="side-pane-window" aria-label={spec.title}>
      <header className="side-pane-window__header">
        <h2 className="side-pane-window__title" title={spec.title}>{spec.title}</h2>
        <div className="side-pane-window__actions">
          {spec.copy && (
            <button
              type="button"
              className={`side-pane-window__icon-btn${justCopied ? ' side-pane-window__icon-btn--ok' : ''}`}
              onClick={onCopy}
              aria-label={justCopied ? 'Copied' : 'Copy'}
              title={justCopied ? 'Copied' : 'Copy'}
            >{justCopied ? '✓' : '⧉'}</button>
          )}
          {spec.download && (
            <button
              type="button"
              className="side-pane-window__icon-btn"
              onClick={onDownload}
              aria-label="Download"
              title="Download"
            >↓</button>
          )}
          <button
            type="button"
            className="side-pane-window__icon-btn"
            onClick={onClickClose}
            aria-label="Close window"
            title="Close window"
          >✕</button>
        </div>
      </header>
      <div className="side-pane-window__body" ref={bodyRef}>
        {spec.render()}
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Run tests; verify all pass.**

Run: `cd src/quodeq/ui && npx vitest run src/features/side-pane/SidePaneWindow.test.jsx`
Expected: 6 tests PASS.

- [ ] **Step 5: Commit.**

```bash
git add src/quodeq/ui/src/features/side-pane/SidePaneWindow.jsx src/quodeq/ui/src/features/side-pane/SidePaneWindow.test.jsx
git commit -m "feat(side-pane): SidePaneWindow component with per-window copy/download/close"
```

---

### Task 6: Build the `SidePane` dock component (vertical stack with horizontal resizers)

**Files:**
- Create: `src/quodeq/ui/src/features/side-pane/SidePane.jsx`
- Create: `src/quodeq/ui/src/features/side-pane/SidePane.test.jsx`
- Create: `src/quodeq/ui/src/features/side-pane/SidePane.css`

The dock renders nothing when `windows` is empty. When non-empty, it renders the right-edge container, the left-edge resize gutter (carrying the styling from the divider commit), and a flex column of `<SidePaneWindow>` instances. Between adjacent windows, render a horizontal drag handle that adjusts the flex ratios of the two adjacent windows.

For v1, all windows have flex-basis of equal share (`flex: 1 1 0` each). Resizing two adjacent windows updates only those two; ratios are kept in component-local state (not persisted), reset on add/remove.

- [ ] **Step 1: Write the failing test file.**

Create `src/quodeq/ui/src/features/side-pane/SidePane.test.jsx`:

```jsx
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { SidePane } from './SidePane.jsx';
import { SidePaneProvider } from './SidePaneProvider.jsx';
import { useSidePane } from './SidePaneContext.jsx';

beforeEach(() => {
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
});

function spec(id, title = id) {
  return { id, type: 'report', title, render: () => <p>{`body:${id}`}</p> };
}

function Adder() {
  const { addWindow } = useSidePane();
  return (
    <div>
      <button onClick={() => addWindow(spec('alpha', 'Alpha'))}>add-a</button>
      <button onClick={() => addWindow(spec('beta', 'Beta'))}>add-b</button>
      <button onClick={() => addWindow(spec('gamma', 'Gamma'))}>add-c</button>
    </div>
  );
}

describe('SidePane', () => {
  it('renders nothing when no windows', () => {
    render(<SidePaneProvider><Adder /><SidePane /></SidePaneProvider>);
    expect(screen.queryByRole('complementary', { name: /side pane/i })).toBeNull();
  });

  it('renders one window with its title and body when one is added', () => {
    render(<SidePaneProvider><Adder /><SidePane /></SidePaneProvider>);
    fireEvent.click(screen.getByText('add-a'));
    expect(screen.getByRole('complementary', { name: /side pane/i })).toBeInTheDocument();
    expect(screen.getByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('body:alpha')).toBeInTheDocument();
  });

  it('renders multiple windows in registration order with a horizontal resizer between them', () => {
    render(<SidePaneProvider><Adder /><SidePane /></SidePaneProvider>);
    fireEvent.click(screen.getByText('add-a'));
    fireEvent.click(screen.getByText('add-b'));
    fireEvent.click(screen.getByText('add-c'));
    const titles = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent);
    expect(titles).toEqual(['Alpha', 'Beta', 'Gamma']);
    const resizers = screen.getAllByRole('separator', { name: /resize/i });
    expect(resizers).toHaveLength(2); // n windows → n-1 resizers
  });

  it('clicking a window close button removes it from the dock', () => {
    render(<SidePaneProvider><Adder /><SidePane /></SidePaneProvider>);
    fireEvent.click(screen.getByText('add-a'));
    fireEvent.click(screen.getByText('add-b'));
    const closes = screen.getAllByRole('button', { name: /close window/i });
    expect(closes).toHaveLength(2);
    fireEvent.click(closes[0]);
    expect(screen.queryByText('Alpha')).toBeNull();
    expect(screen.getByText('Beta')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests; expect them to fail.**

Run: `cd src/quodeq/ui && npx vitest run src/features/side-pane/SidePane.test.jsx`
Expected: import error for `SidePane`.

- [ ] **Step 3: Create `SidePane.jsx`.**

```jsx
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useSidePane } from './SidePaneContext.jsx';
import { SidePaneWindow } from './SidePaneWindow.jsx';
import { clampSidePaneWidth } from './paneWidthMath.js';
import './SidePane.css';

const MIN_WINDOW_RATIO = 0.1;

export function SidePane() {
  const { windows, isOpen, paneWidth, setPaneWidth, removeWindow } = useSidePane();

  // Per-resizer ratios: ratios[i] in [0,1] is the share of (windows[i] + windows[i+1])
  // that goes to windows[i]. Reset whenever the window count changes (structural reset).
  const [ratios, setRatios] = useState(() => Array(Math.max(0, windows.length - 1)).fill(0.5));
  useEffect(() => {
    setRatios(Array(Math.max(0, windows.length - 1)).fill(0.5));
  }, [windows.length]);

  // Outer pane (left-edge) drag — resizes the whole dock width.
  const [isDragging, setIsDragging] = useState(false);
  const onOuterDividerPointerDown = useCallback((e) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = paneWidth;
    const viewport = window.innerWidth;
    setIsDragging(true);
    const prevCursor = document.body.style.cursor;
    const prevSelect = document.body.style.userSelect;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    const onMove = (ev) => {
      const delta = startX - ev.clientX;
      const next = clampSidePaneWidth(startWidth + delta, viewport);
      document.documentElement.style.setProperty('--side-pane-width', `${next}px`);
    };
    const onUp = (ev) => {
      const delta = startX - ev.clientX;
      setPaneWidth(clampSidePaneWidth(startWidth + delta, window.innerWidth));
      setIsDragging(false);
      document.body.style.cursor = prevCursor;
      document.body.style.userSelect = prevSelect;
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [paneWidth, setPaneWidth]);

  // Internal between-window resizer.
  const containerRef = useRef(null);
  const onInnerDividerPointerDown = useCallback((index) => (e) => {
    e.preventDefault();
    const startY = e.clientY;
    const startRatio = ratios[index] ?? 0.5;
    const container = containerRef.current;
    if (!container) return;
    // Total pixel span of the two adjacent windows = their combined offsetHeight.
    const aEl = container.querySelectorAll('.side-pane-window')[index];
    const bEl = container.querySelectorAll('.side-pane-window')[index + 1];
    const span = (aEl?.offsetHeight ?? 0) + (bEl?.offsetHeight ?? 0);
    if (span <= 0) return;
    const onMove = (ev) => {
      const delta = ev.clientY - startY;
      const next = Math.min(1 - MIN_WINDOW_RATIO, Math.max(MIN_WINDOW_RATIO, startRatio + delta / span));
      setRatios((prev) => {
        const out = [...prev];
        out[index] = next;
        return out;
      });
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [ratios]);

  if (!isOpen) return null;

  const flexBases = windows.map((_, i) => {
    // Compute each window's flex value from the cumulative ratio products.
    // For v1 simplicity: render each window as flex: <weight> 1 0 where weights
    // come from the ratios chain. Approach: start from equal weights, then for
    // each ratio[i], rebalance windows[i] vs windows[i+1] to that share of their
    // *combined* weight. This keeps untouched neighbors unchanged.
    return 1; // placeholder; we'll rewrite below
  });

  // Build weights from ratios: walk through, treating each ratios[i] as the
  // split between weights[i] and weights[i+1] of their combined share.
  const weights = Array(windows.length).fill(1);
  for (let i = 0; i < ratios.length; i += 1) {
    const r = ratios[i] ?? 0.5;
    const sum = weights[i] + weights[i + 1];
    weights[i] = sum * r;
    weights[i + 1] = sum * (1 - r);
  }

  return (
    <aside
      className="side-pane"
      role="complementary"
      aria-label="Side pane"
      ref={containerRef}
    >
      <div
        className={`side-pane__divider${isDragging ? ' side-pane__divider--dragging' : ''}`}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize side pane"
        onPointerDown={onOuterDividerPointerDown}
      />
      {windows.map((spec, i) => (
        <React.Fragment key={spec.id}>
          <div className="side-pane-window-slot" style={{ flex: `${weights[i]} 1 0` }}>
            <SidePaneWindow spec={spec} onClose={removeWindow} />
          </div>
          {i < windows.length - 1 && (
            <div
              className="side-pane__row-divider"
              role="separator"
              aria-orientation="horizontal"
              aria-label={`Resize between window ${i + 1} and ${i + 2}`}
              onPointerDown={onInnerDividerPointerDown(i)}
            />
          )}
        </React.Fragment>
      ))}
    </aside>
  );
}
```

- [ ] **Step 4: Create `SidePane.css`.**

Adapt the divider-styling commit's CSS, scoped to the new class names:

```css
/* ── Pane container ───────────────────────────────────── */
.side-pane {
  position: relative;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--color-surface);
  color: var(--color-text);
  border-radius: 0;
  overflow: visible;
  min-width: 0;
  margin-left: 0;
}

/* ── Left-edge resize gutter (between main column and pane) ─────────── */
.side-pane__divider {
  position: absolute;
  top: 0;
  left: -8px;
  width: 8px;
  height: 100%;
  cursor: col-resize;
  z-index: 1;
  background: var(--color-surface-alt);
  opacity: 0.5;
  transition: opacity 120ms ease;
}
.side-pane__divider:hover,
.side-pane__divider--dragging {
  opacity: 0.85;
}

/* ── Window slot ─────────────────────────────────────── */
.side-pane-window-slot {
  display: flex;
  min-height: 0;
  overflow: hidden;
}
.side-pane-window {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-height: 0;
  overflow: hidden;
}

/* ── Window header ───────────────────────────────────── */
.side-pane-window__header {
  flex: 0 0 auto;
  height: 36px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface-alt);
}
.side-pane-window__title {
  flex: 1 1 auto;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.side-pane-window__actions {
  display: flex;
  gap: 4px;
}
.side-pane-window__icon-btn {
  background: transparent;
  border: 1px solid transparent;
  color: var(--color-text-muted);
  width: 24px;
  height: 24px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
}
.side-pane-window__icon-btn:hover {
  background: var(--color-surface-alt);
  color: var(--color-text);
}
.side-pane-window__icon-btn--ok,
.side-pane-window__icon-btn--ok:hover {
  color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
}

/* ── Window body ─────────────────────────────────────── */
.side-pane-window__body {
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 12px 16px;
  line-height: 1.55;
}

/* ── Between-windows resizer ─────────────────────────── */
.side-pane__row-divider {
  flex: 0 0 4px;
  background: var(--color-border);
  cursor: row-resize;
  opacity: 0.4;
  transition: opacity 120ms ease;
}
.side-pane__row-divider:hover {
  opacity: 0.85;
}
```

- [ ] **Step 5: Run tests; verify all pass.**

Run: `cd src/quodeq/ui && npx vitest run src/features/side-pane/SidePane.test.jsx`
Expected: 4 tests PASS.

- [ ] **Step 6: Commit.**

```bash
git add src/quodeq/ui/src/features/side-pane/SidePane.jsx src/quodeq/ui/src/features/side-pane/SidePane.test.jsx src/quodeq/ui/src/features/side-pane/SidePane.css
git commit -m "feat(side-pane): SidePane dock with vertical stack and inter-window resizers"
```

---

### Task 7: Add the barrel `index.js` for the new feature

**Files:**
- Create: `src/quodeq/ui/src/features/side-pane/index.js`

- [ ] **Step 1: Create the index.**

```js
export { SidePane } from './SidePane.jsx';
export { SidePaneProvider } from './SidePaneProvider.jsx';
export { useSidePane } from './SidePaneContext.jsx';
export { useRegisterWindowSpec } from './useRegisterWindowSpec.js';
export { ReportContent } from './reportContent.jsx';
```

- [ ] **Step 2: Commit.**

```bash
git add src/quodeq/ui/src/features/side-pane/index.js
git commit -m "feat(side-pane): barrel index for the new feature module"
```

---

### Task 8: Update `App.jsx` to mount the new provider + dock

**Files:**
- Modify: `src/quodeq/ui/src/App.jsx`

- [ ] **Step 1: Replace imports.**

In `App.jsx`, change the report-viewer imports to side-pane. Replace:

```jsx
import { ReportPane } from './features/report-viewer/ReportPane.jsx';
```

with:

```jsx
import { SidePane } from './features/side-pane/index.js';
```

If there's a `ReportViewerProvider` wrapping `<App>` (likely in `main.jsx` or near the App tree), replace it with `SidePaneProvider`. Search:

```bash
grep -rn "ReportViewerProvider\|useReportViewer" src/quodeq/ui/src --include='*.jsx' --include='*.js'
```

Update every file to use `SidePaneProvider` / `useSidePane` accordingly. (Most are in pages handled by Tasks 9 and 10; this task handles only `App.jsx` and the root mount.)

- [ ] **Step 2: Replace the `<ReportPane />` mount with `<SidePane />`.**

In `App.jsx` line 287 (the spot that had `<ReportPane />`), use `<SidePane />`.

- [ ] **Step 3: Build is run only at the end (Task 12); no test command for this step.**

- [ ] **Step 4: Commit.**

```bash
git add src/quodeq/ui/src/App.jsx src/quodeq/ui/src/main.jsx
git commit -m "refactor(app): mount SidePaneProvider + SidePane in place of ReportPane"
```

(If `main.jsx` was untouched because the provider is mounted elsewhere, just commit `App.jsx`.)

---

### Task 9: Update `TopBar` — per-type buttons + close-all

**Files:**
- Modify: `src/quodeq/ui/src/components/TopBar.jsx`

- [ ] **Step 1: Replace the Report button block + add the close-all button.**

In `TopBar.jsx`, change the destructure on line 76 from `useReportViewer()` to use the side-pane API, plus a child `ReportToolbarButton` that consumes `useRegisterWindowSpec`. Cleanest layout: define the per-type buttons inline near the top of the file or as small helpers in the same file (don't lift to separate files unless they grow).

Imports:

```jsx
import { useSidePane } from '../features/side-pane/index.js';
```

Inside `TopBar`:

```jsx
const { isOpen: paneOpen, closeAll } = useSidePane();
```

Replace the existing `{activeBuilder && (<button…>Report</button>)}` block (lines 132–142 after the previous TopBar change, or 132–151 in the original) with:

```jsx
<ReportToolbarButton />
{paneOpen && (
  <button
    type="button"
    className="topbar-btn topbar-btn--icon topbar-btn--close-pane"
    onClick={closeAll}
    aria-label="Close all side-pane windows"
    title="Close all"
  >
    <CloseIcon />
  </button>
)}
```

Where `ReportToolbarButton` is a tiny inline component defined above `TopBar` (or at the bottom of the file):

```jsx
function ReportToolbarButton() {
  // Pages that have no report register a null spec via useRegisterWindowSpec.
  // The button is rendered only when a spec is registered.
  const ctx = useSidePane();
  const spec = ctx.getRegisteredSpec ? ctx.getRegisteredSpec('report') : null;
  if (!spec) return null;
  const inDock = ctx.hasWindow(spec.id);
  const atCap = ctx.windows.length >= ctx.MAX_WINDOWS && !inDock;
  return (
    <button
      type="button"
      className={`topbar-btn topbar-btn--report${inDock ? ' topbar-btn--report--open' : ''}`}
      aria-pressed={inDock}
      disabled={atCap}
      title={atCap ? 'Close a window to open another' : (inDock ? 'Close report' : 'Open report')}
      onClick={() => {
        if (inDock) ctx.removeWindow(spec.id);
        else ctx.addWindow(spec);
      }}
    >
      <FileTextIcon />
      <span>Report</span>
    </button>
  );
}
```

`CloseIcon` doesn't exist yet — add it next to the existing icon imports in this file (or define inline as a small `<svg>` using the same style as the other icons in the file). Pick whatever is consistent with existing icons.

- [ ] **Step 2: Commit.**

```bash
git add src/quodeq/ui/src/components/TopBar.jsx
git commit -m "feat(topbar): per-type window buttons + close-all icon"
```

---

### Task 10: Migrate `AccumulatedOverviewPanel` to `useRegisterWindowSpec`

**Files:**
- Modify: `src/quodeq/ui/src/features/dashboard/components/AccumulatedOverviewPanel.jsx`

- [ ] **Step 1: Replace the report-viewer hook usage.**

In `AccumulatedOverviewPanel.jsx`:

Replace import:
```jsx
import { useReportViewer } from '../../report-viewer/index.js';
```
with:
```jsx
import { useRegisterWindowSpec, ReportContent } from '../../side-pane/index.js';
```

Replace the existing `useReportViewer` + `useEffect(setActiveBuilder…)` block (lines 184–206 in the current file) with:

```jsx
const reportProjectName =
  data.projectInfo?.displayName
  || data.projectInfo?.name
  || data.selectedDisplayName
  || data.selectedProject
  || 'project';
const hasReportData = Boolean(
  filteredAccumulated?.summary
  && Number.isFinite(parseFloat(filteredAccumulated.summary.numericAverage))
  && (filteredDimensions?.length ?? 0) > 0
);
const reportSpec = React.useMemo(() => {
  if (!hasReportData) return null;
  const markdown = () => buildOverviewReport(filteredAccumulated, filteredDimensions || [], reportProjectName);
  return {
    id: `report:overview:${reportProjectName}`,
    type: 'report',
    title: `Code Quality Report — ${reportProjectName}`,
    render: () => <ReportContent markdown={markdown()} />,
    copy: () => markdown(),
    download: () => ({ filename: `code-quality-report-${reportProjectName}.md`, body: markdown() }),
  };
}, [hasReportData, reportProjectName, filteredAccumulated, filteredDimensions]);
useRegisterWindowSpec('report', reportSpec);
```

If `React` isn't already imported at the top of the file, add it (`import React from 'react'`).

- [ ] **Step 2: Smoke-build by running its tests if any exist.**

Run: `cd src/quodeq/ui && npx vitest run src/features/dashboard/`
Expected: pass (or no tests found for this component).

- [ ] **Step 3: Commit.**

```bash
git add src/quodeq/ui/src/features/dashboard/components/AccumulatedOverviewPanel.jsx
git commit -m "refactor(overview): migrate to useRegisterWindowSpec"
```

---

### Task 11: Migrate `ExplorerPage` to `useRegisterWindowSpec`

**Files:**
- Modify: `src/quodeq/ui/src/features/explorer/components/ExplorerPage.jsx`

- [ ] **Step 1: Replace the report-viewer hook usage.**

In `ExplorerPage.jsx`:

Replace import:
```jsx
import { useReportViewer } from '../../report-viewer/index.js';
```
with:
```jsx
import { useRegisterWindowSpec, ReportContent } from '../../side-pane/index.js';
```

Replace the existing `useReportViewer` + `useEffect(setActiveBuilder…)` block (lines 154–174) with:

```jsx
const reportSpec = React.useMemo(() => {
  if (!d.evalData) return null;
  const dim = d.evalData.dimension || 'Unknown';
  const dimTitle = dim.charAt(0).toUpperCase() + dim.slice(1);
  const markdown = () => buildDimensionReport({
    evalData: d.evalData,
    principleGrades: d.principleGrades || [],
    allViolations: filteredViolations,
    overallGrade: d.overallGrade,
    dateLabel,
    runId,
  });
  return {
    id: `report:dimension:${dim}:${runId ?? 'current'}`,
    type: 'report',
    title: `${dimTitle} Report`,
    render: () => <ReportContent markdown={markdown()} />,
    copy: () => markdown(),
    download: () => ({ filename: `${dim}-report.md`, body: markdown() }),
  };
}, [d.evalData, d.principleGrades, filteredViolations, d.overallGrade, dateLabel, runId]);
useRegisterWindowSpec('report', reportSpec);
```

If `React` isn't already imported, add it.

- [ ] **Step 2: Smoke-build by running its tests if any exist.**

Run: `cd src/quodeq/ui && npx vitest run src/features/explorer/`
Expected: pass (or no tests found).

- [ ] **Step 3: Commit.**

```bash
git add src/quodeq/ui/src/features/explorer/components/ExplorerPage.jsx
git commit -m "refactor(explorer): migrate to useRegisterWindowSpec"
```

---

### Task 12: Delete the old report-viewer module + rename CSS variable

**Files:**
- Delete: `src/quodeq/ui/src/features/report-viewer/` (entire directory; only the leftover obsolete files should remain at this point)
- Modify: `src/quodeq/ui/src/styles/terminal.css` (rename `--report-pane-width` → `--side-pane-width`)

- [ ] **Step 1: Confirm no remaining references.**

Run:
```bash
grep -rn "report-viewer\|useReportViewer\|ReportPane\|ReportViewerProvider\|--report-pane-width" src/quodeq/ui/src
```
Expected: zero hits in source files (only in this very file as the search itself, which doesn't count). If any remain, fix them before deletion.

- [ ] **Step 2: Rename the CSS variable in `terminal.css`.**

Edit `src/quodeq/ui/src/styles/terminal.css`: change all occurrences of `--report-pane-width` to `--side-pane-width` (lines 1353 and 1363, plus any others surfaced by the grep).

- [ ] **Step 3: Delete the old directory.**

```bash
git rm -r src/quodeq/ui/src/features/report-viewer
```

- [ ] **Step 4: Run the full UI suite.**

Run: `cd src/quodeq/ui && npx vitest run`
Expected: all tests PASS, no broken imports.

- [ ] **Step 5: Commit.**

```bash
git add -A
git commit -m "chore(side-pane): drop old report-viewer module + rename CSS variable"
```

---

### Task 13: Run full UI test suite + manual smoke

- [ ] **Step 1: Full vitest run.**

Run: `cd src/quodeq/ui && npx vitest run`
Expected: all tests PASS.

- [ ] **Step 2: Build the dev dashboard and smoke in browser.**

Run from repo root: `uv run quodeq dashboard --dev`

Manual checks:
1. On overview, click **Report** → window appears in dock with overview report.
2. Navigate to a standard's detail. Existing overview window still visible. Click **Report** → second window appears below; pane stays at full width, two windows split equally.
3. Add a third window from another page → all three split equally; close-all icon appears in topbar.
4. Try to open a 4th → toolbar Report button is disabled with tooltip "Close a window to open another".
5. Close one window via its X → remaining ones rebalance equally; close-all stays.
6. Drag the horizontal bar between two windows → ratios update; release commits.
7. Drag the left gutter → pane width changes; persists across page reloads (`localStorage.quodeq.sidePaneWidth`).
8. Esc with pane open → all windows close, dock collapses, close-all icon hides.
9. Reload the page mid-session → pane is empty (no persistence of windows; only paneWidth).
10. Reload again with `localStorage.quodeq.reportPaneWidth` set in devtools → migration runs, value moves to the new key.
11. Toolbar Report button toggles correctly: clicking when this page's window is in the dock removes it; clicking again re-adds.

If anything misbehaves, no separate task — fix with a follow-up commit.

---

## Self-review

- ✅ Spec coverage: every behavior in the design (multi-window, cap=3, no auto-close, per-window chrome, close-all, Esc, gutter resize, inter-window resize, page-aware toolbar buttons) maps to a task.
- ✅ No placeholders — every step has runnable commands or concrete code.
- ✅ Type/identifier consistency: `useSidePane`, `SidePane`, `SidePaneProvider`, `useRegisterWindowSpec`, `--side-pane-width`, `quodeq.sidePaneWidth`, `MAX_WINDOWS = 3`, `clampSidePaneWidth` — used consistently across tasks.
- ✅ Migration story: legacy localStorage key + legacy CSS variable both renamed, with a one-shot read-side migration for the localStorage key.
- ✅ Files referenced (`ReportViewerProvider.jsx`, `TopBar.jsx`, `App.jsx`, `ExplorerPage.jsx`, `AccumulatedOverviewPanel.jsx`, `terminal.css`) all exist.
