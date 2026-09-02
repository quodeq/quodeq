import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { resolveTerminalPaths, openInEditor } from '../../api/terminal.js';
import { createUrlLinkProvider, createFileLinkProvider } from './terminalLinks.js';
import { themeFromCss } from './xtermTheme.js';
import { openExternal } from '../updates/openExternal.js';

// Two drawer chords are reserved for the host; return false so xterm lets them
// bubble to the window handler instead of typing into the shell.
export function isReservedChord(e) {
  return e.code === 'Backquote' && (e.ctrlKey || e.metaKey);
}

/**
 * TerminalSessionView.jsx's xterm instance + link-provider setup, extracted
 * verbatim (the observer glue -- ResizeObserver/MutationObserver, the
 * debounced scheduleFit, and the initial fit-if-visible check -- stays
 * inline in the mount effect, per the split's scope).
 */
export function createTerminalInstance({ rootEl, sessionId, send }) {
  // A real terminal font (Menlo = macOS Terminal default, Monaco = iTerm's
  // classic default), NOT the code-panel's JetBrains Mono. All system fonts
  // — available synchronously, so xterm measures the cell correctly with no
  // webfont race (JBM, a Google webfont, caused the extra-spacing bug).
  const term = new Terminal({
    scrollback: 5000,
    fontFamily: 'Menlo, Monaco, "SF Mono", "SFMono-Regular", Consolas, "DejaVu Sans Mono", monospace',
    fontSize: 13,
    // iTerm-tight vertical rhythm. 1.5 read like a text editor (too airy);
    // iTerm's default is ~1.0 — 1.1 keeps a hair of breathing room.
    lineHeight: 1.1,
    cursorBlink: true,
    cursorStyle: 'bar',     // sleeker than the default square block
    theme: themeFromCss(),
    // OSC 8 hyperlinks (emitted by gh, npm, coding CLIs…) are handled by
    // xterm itself, not by our link providers below. Without a linkHandler
    // xterm falls back to its built-in one, which confirms and then calls
    // window.open() with no URL — and window.open always returns null
    // inside pywebview's WKWebView, so clicking OK does nothing at all.
    // Route them through openExternal, which prefers the pywebview bridge.
    linkHandler: { activate: (_event, uri) => openExternal(uri) },
  });
  const fit = new FitAddon();
  term.loadAddon(fit);
  term.open(rootEl);
  term.attachCustomKeyEventHandler((e) => !isReservedChord(e));
  term.onData((d) => send(d));

  const linkProviders = registerLinkProviders(term, sessionId);

  return { term, fit, linkProviders };
}

// Clickable links: cmd/ctrl-click a URL to open it in the system browser, or
// a real file path to open it in the user's editor. The file provider asks
// the backend which candidates are real files before lighting them up (see
// terminalLinks.js); resolution runs against THIS session's shell cwd. y is
// a 1-based buffer line number.
function registerLinkProviders(term, sessionId) {
  const readLine = (y) => term.buffer.active.getLine(y - 1)?.translateToString(true) ?? '';
  return [
    term.registerLinkProvider(createUrlLinkProvider({
      readLine,
      // Not window.open: it returns null in the desktop app's WKWebView,
      // so a cmd-clicked URL silently did nothing there.
      openUrl: (url) => openExternal(url),
    })),
    term.registerLinkProvider(createFileLinkProvider({
      readLine,
      resolvePaths: (paths) => resolveTerminalPaths(paths, sessionId),
      openFile: (abs, line, col) => { openInEditor(abs, line, col, sessionId).catch(() => {}); },
    })),
  ];
}
