/**
 * KeyHint — keyboard shortcut badges, e.g. `⏎`, `esc`, or `g o`.
 * Pass a single key string or an array of strings; arrays render as a sequence
 * of `<kbd>` elements joined by a subtle `+` or space.
 *
 * @param {object} props
 * @param {string | string[]} props.keys
 * @param {'plus'|'space'} [props.joiner='space']
 */
// The only non-default `joiner` value (the default is 'space').
const JOINER_PLUS = 'plus';

export default function KeyHint({ keys, joiner = 'space' }) {
  const arr = Array.isArray(keys) ? keys : [keys];
  const sep = joiner === JOINER_PLUS ? '+' : ' ';
  return (
    <span className="term-key-hint">
      {arr.map((k, i) => (
        <span key={i} className="term-key-hint__group">
          <kbd className="term-key-hint__kbd">{k}</kbd>
          {i < arr.length - 1 && <span className="term-key-hint__sep" aria-hidden="true">{sep}</span>}
        </span>
      ))}
    </span>
  );
}
