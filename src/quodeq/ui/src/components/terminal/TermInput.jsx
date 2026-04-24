/**
 * TermInput — terminal-style text input prefixed with a shell prompt
 * (e.g. `$ grep -r [input...]`).
 *
 * @param {object} props
 * @param {string}  [props.prompt='$']
 * @param {string}  [props.command]          Static command shown between prompt and input (e.g. 'grep -r').
 * @param {string}  [props.placeholder]
 * @param {string}  props.value
 * @param {(next: string) => void} props.onChange
 * @param {() => void} [props.onSubmit]
 * @param {string}  [props.id]
 * @param {string}  [props.name]
 * @param {string}  [props.ariaLabel]
 */
export default function TermInput({
  prompt = '$',
  command,
  placeholder,
  value,
  onChange,
  onSubmit,
  id,
  name,
  ariaLabel,
}) {
  return (
    <div className="term-input">
      <span className="term-input__prompt" aria-hidden="true">{prompt}</span>
      {command && <span className="term-input__command">{command}</span>}
      <input
        type="text"
        className="term-input__field"
        id={id}
        name={name}
        aria-label={ariaLabel || command || 'input'}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && onSubmit) onSubmit();
        }}
        spellCheck={false}
        autoComplete="off"
      />
    </div>
  );
}
