import { useEffect, useState } from 'react';

/**
 * Whether a galaxy view has faded in: false until `ready` is first truthy,
 * then true for the life of the view.
 *
 * @param {unknown} ready
 * @returns {boolean}
 */
export function useFadeIn(ready) {
  const [visible, setVisible] = useState(false);
  useEffect(() => { if (ready) setVisible(true); }, [ready]);
  return visible;
}

/**
 * The fading frame and focusable canvas both galaxy views draw into.
 * `handlers` supplies the canvas mouse, key and focus events; `children`
 * render over the canvas inside the frame.
 */
export default function GalaxyCanvas({ visible, canvasRef, size, label, handlers, children }) {
  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', opacity: visible ? 1 : 0, transition: 'opacity 0.4s ease' }}>
      <canvas
        className="viz-focusable"
        ref={canvasRef}
        width={size.w}
        height={size.h}
        style={{ width: '100%', height: '100%', display: 'block' }}
        tabIndex={0}
        role="application"
        aria-label={label}
        onMouseMove={handlers.handleMouseMove}
        onMouseLeave={handlers.handleMouseLeave}
        onClick={handlers.handleClick}
        onKeyDown={handlers.handleKeyDown}
        onFocus={handlers.handleFocus}
        onBlur={handlers.handleBlur}
      />
      {children}
    </div>
  );
}
