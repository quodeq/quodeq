/**
 * galaxyTuning.js — the drawing tunables the two galaxy views share.
 *
 * GalaxyView (dimensions and principles) and GalaxyFolderView (folders and
 * files) paint the same furniture: a radial background wash over a twinkling
 * starfield, pulsing stars, nebula discs with orbiting texture blobs, and
 * labelled violation orbs once the zoom is deep enough. The numbers that
 * shape all of that live here, so one tweak lands in both views instead of
 * drifting between the draw modules.
 *
 * Zoom breakpoints, tooltip placement and the default canvas box live in
 * ../core/galaxyTunables.js instead — those are read by the event, layout
 * and hook modules too, not only by the painters. Anything only one module
 * uses stays a `const` at the top of that module.
 *
 * Units are in the field names: `Px` screen pixels, `S` seconds, `Fraction`
 * a 0..1 multiple of some other length, `Alpha` a 0..1 opacity. A speed is
 * radians per time unit (`t`, which the animation loop advances by
 * CAMERA.frameStepS per frame) unless a comment says otherwise; a count is
 * unitless. Every object is frozen: they are module-scope singletons read on
 * every animation frame, never per-frame allocations.
 */

/**
 * The radial background wash, and how the starfield over it is painted. The
 * field itself is built by galaxyCore's mkBackgroundStars, which owns the
 * count and the per-star ranges; these are the painter's numbers.
 */
export const BACKGROUND = Object.freeze({
  // Gradient radius, as a fraction of the canvas's longer side.
  gradientRadiusFraction: 0.6,
  // Each star breathes between base-amp and base+amp.
  starAlphaBase: 0.15,
  starAlphaAmp: 0.15,
});

/** A star's idle pulse, and how its world radius becomes screen pixels. */
export const STAR = Object.freeze({
  // The pulse scales the radius between 1-amplitude and 1+amplitude.
  pulseAmplitude: 0.01,
  pulseSpeed: 0.4,
  // Screen radius is `radius * pulse * cam.z * screenRadiusFraction`.
  screenRadiusFraction: 0.5,
});

/**
 * The scene-wide nebula: one very faint disc centred on the canvas, tinted
 * by the current compliance score. The alphas are deliberately tiny — it is
 * a wash behind the stars, not a shape of its own.
 */
export const NEBULA = Object.freeze({
  // Disc radius as a fraction of the canvas's longer side.
  sceneRadiusFraction: 0.7,
  sceneCentreAlpha: 0.015,
  sceneMidAlpha: 0.007,
  // Where the mid colour stop sits between centre and edge.
  midStopOffset: 0.5,
  // Alpha of the texture blobs orbiting over the scene disc.
  sceneBlobAlpha: 0.008,
});

/**
 * The fixed shape of a nebula's blob ring. Both nebulas draw the same ring
 * at their own count, speed, alpha and size; the frame's `t` is merged in
 * once per frame so a folder star, which draws once per star per frame,
 * allocates nothing.
 *
 * `spin` and `wobble` are radians per time unit, `orbit` is the blob
 * centre's distance from the disc centre as a fraction of the disc radius,
 * `sizeBase`/`sizeAmp` are the blob radius as a fraction of it, and
 * `wobbleStep` is the phase offset between consecutive blobs.
 */
export const NEBULA_SCENE_BLOBS = Object.freeze({
  count: 4, spin: 0.005, orbit: 0.35, sizeBase: 0.3, sizeAmp: 0.08,
  wobble: 0.015, wobbleStep: 1.7,
});

/** The same ring over a folder cluster's nebula: fewer, faster, bigger blobs. */
export const NEBULA_FOLDER_BLOBS = Object.freeze({
  count: 3, spin: 0.01, orbit: 0.3, sizeBase: 0.4, sizeAmp: 0.1,
  wobble: 0.02, wobbleStep: 2,
});

/**
 * The labelled violation orbs both views swap in at deep zoom: the galaxy
 * view around a selected principle, the folder view around a flagged file.
 * Same orbit maths, same twinkle, same label treatment in both.
 */
export const VIOLATION_ORBS = Object.freeze({
  // Orbit distance and orb size are both `cam.z * scaleFraction`.
  scaleFraction: 0.06,
  // Each orb's brightness breathes between base-amp and base+amp.
  twinkleBase: 0.5,
  twinkleAmp: 0.06,
  twinkleSpeed: 0.4,
  // Drawn radius is `particle size * scale * radiusFraction`.
  radiusFraction: 0.5,
  // A severity name is only worth drawing once the orb is this big.
  labelMinRadiusPx: 3,
  labelFontMinPx: 7,
  labelFontMaxPx: 11,
  labelFontRadiusFraction: 0.8,
  labelAlpha: 0.85,
  labelOffsetPx: 4,
});

/**
 * The animation clock and the framing rules both camera hooks obey. The
 * easing curves themselves are in galaxyEasing.js; the per-view lerp rates
 * and view margins stay in their own hooks, because the two views really do
 * chase their targets at different speeds.
 */
export const CAMERA = Object.freeze({
  // The loop advances `t` by a fixed step rather than by wall-clock delta,
  // so a dropped frame slows the animation instead of jumping it. One step
  // is one frame at 60 fps.
  frameStepS: 0.016,
  // Frames right after a scene swap that jump straight to the target rather
  // than lerping toward it, so a new scene opens already framed.
  snapFrames: 3,
  // Fitting a scene may zoom out as far as it likes but never in past this.
  fitZoomMax: 4,
});
