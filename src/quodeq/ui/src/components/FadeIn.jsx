import { useState } from 'react';

const FADE_PHASES = ['a', 'b'];

/**
 * Fades its children in whenever `restartKey` changes, without remounting
 * them. The wrapper node is stable; the animation restarts because
 * `data-fade` alternates between two phases that select identical keyframes
 * (a CSS animation only restarts when its `animation-name` changes). A keyed
 * remount would drop the children's state and refire their mount effects.
 * `className` must carry the `tab-fadein` / `tab-fadein-alt` pair. A nullish
 * key means "nothing to show yet" and does not restart the fade.
 */
export default function FadeIn({ restartKey, className, style, children }) {
  const [fade, setFade] = useState({ key: restartKey, phase: 0 });
  if (restartKey != null && fade.key !== restartKey) setFade({ key: restartKey, phase: (fade.phase + 1) % FADE_PHASES.length });
  return (
    <div className={className} data-fade={FADE_PHASES[fade.phase]} style={style}>
      {children}
    </div>
  );
}
