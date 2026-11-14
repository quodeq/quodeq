import { useRef } from 'react';
import { KEY } from '../../vocab/keyboard.js';
import { edgeEnabled, matchTypeahead, stepEnabled } from './selectOptions.js';

const TYPEAHEAD_RESET_MS = 500; // a pause this long starts a new typed search
const OPEN_KEYS = [KEY.ARROW_DOWN, KEY.ARROW_UP, KEY.ENTER, KEY.SPACE];

const isTypedCharacter = (e) => e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey;

function useTypeahead() {
  const typed = useRef({ text: '', at: 0 });
  return (char) => {
    const now = Date.now();
    const text = now - typed.current.at > TYPEAHEAD_RESET_MS ? char : typed.current.text + char;
    typed.current = { text, at: now };
    return text;
  };
}

/** The Select trigger's keydown handler: the keyboard behaviour of a native select. */
export function useSelectKeyboard({ open, active, setActive, flat, show, close, pick }) {
  const typeahead = useTypeahead();

  const moves = {
    [KEY.ARROW_DOWN]: () => setActive(stepEnabled(flat, active, 1)),
    [KEY.ARROW_UP]: () => setActive(stepEnabled(flat, active, -1)),
    [KEY.HOME]: () => setActive(edgeEnabled(flat, 1)),
    [KEY.END]: () => setActive(edgeEnabled(flat, -1)),
    [KEY.ENTER]: () => pick(active),
    [KEY.SPACE]: () => pick(active),
    // Stops here so a popover around this Select stays open: only the list closes.
    [KEY.ESCAPE]: close,
  };

  const onOpenKeyDown = (e) => {
    const move = moves[e.key];
    if (e.key === KEY.TAB) { close(); return; }
    if (move) {
      e.preventDefault();
      e.stopPropagation();
      move();
    } else if (isTypedCharacter(e)) {
      const match = matchTypeahead(flat, typeahead(e.key));
      if (match >= 0) setActive(match);
    }
  };

  return (e) => {
    if (open) { onOpenKeyDown(e); return; }
    if (OPEN_KEYS.includes(e.key)) {
      e.preventDefault();
      show();
    }
  };
}
