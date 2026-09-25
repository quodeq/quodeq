// KeyboardEvent.key values the UI branches on. Values are the DOM spec's
// names, never localised.
export const KEY = Object.freeze({
  ENTER: 'Enter',
  ESCAPE: 'Escape',
  TAB: 'Tab',
  ARROW_UP: 'ArrowUp',
  ARROW_DOWN: 'ArrowDown',
  ARROW_LEFT: 'ArrowLeft',
  ARROW_RIGHT: 'ArrowRight',
});

// KeyboardEvent.code values the UI branches on: physical-key identity
// (layout-independent), unlike KEY above which is the character/name from
// .key. Only the drawer's Ctrl/Cmd+` toggle (useDrawerHotkeys.js) and the
// embedded terminal's matching guard (terminalSetup.js) need one, so they
// don't fire the shortcut back into the terminal itself.
export const KEY_CODE = Object.freeze({ BACKQUOTE: 'Backquote' });
