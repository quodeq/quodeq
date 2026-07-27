// Builds the xterm theme from the live CSS tokens so the console follows the
// app-level theme (data-theme attribute). All --tty-ansi-* tokens resolve to
// plain hex/rgba in tokens.css — xterm parses colors itself and cannot
// evaluate color-mix()/var() indirection.
export function themeFromCss() {
  const s = getComputedStyle(document.documentElement);
  const v = (name, fb) => (s.getPropertyValue(name).trim() || fb);
  return {
    background: v('--color-surface-alt', '#1e1e1e'),
    foreground: v('--color-text', '#dcdcdc'),
    cursor: v('--color-accent', '#dcdcdc'),
    selectionBackground: v('--tty-selection', 'rgba(255,255,255,0.22)'),
    black: v('--tty-ansi-black', '#1a2230'),
    red: v('--tty-ansi-red', '#e05c4b'),
    green: v('--tty-ansi-green', '#4caf7d'),
    yellow: v('--tty-ansi-yellow', '#fbbf24'),
    blue: v('--tty-ansi-blue', '#5aa2e8'),
    magenta: v('--tty-ansi-magenta', '#c987c9'),
    cyan: v('--tty-ansi-cyan', '#22d3ee'),
    white: v('--tty-ansi-white', '#d4e0f0'),
    brightBlack: v('--tty-ansi-bright-black', '#4a6a88'),
    brightRed: v('--tty-ansi-bright-red', '#f05078'),
    brightGreen: v('--tty-ansi-bright-green', '#6fd49a'),
    brightYellow: v('--tty-ansi-bright-yellow', '#fcd34d'),
    brightBlue: v('--tty-ansi-bright-blue', '#82bcf4'),
    brightMagenta: v('--tty-ansi-bright-magenta', '#dfa8df'),
    brightCyan: v('--tty-ansi-bright-cyan', '#67e3f9'),
    brightWhite: v('--tty-ansi-bright-white', '#ffffff'),
  };
}
