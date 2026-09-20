/**
 * galaxyTuning.js — the numbers that shape the two galaxy visualizations.
 *
 * GalaxyView (dimensions and principles) and GalaxyFolderView (folders and
 * files) paint the same furniture: a radial background wash over a twinkling
 * starfield, pulsing stars, nebula discs with orbiting texture blobs, and
 * labelled violation orbs once the zoom is deep enough. The first section
 * below holds what both views share, so one tweak lands in both; the two
 * after it hold each view's own furniture, kept here rather than inline so
 * the draw modules stay readable drawing code.
 *
 * Zoom breakpoints, tooltip placement and the default canvas box live in
 * ../core/galaxyTunables.js instead — those are read by the event, layout
 * and hook modules too, not only by the painters. Particle and starfield
 * *generation* ranges live with their builders in ../core/galaxyCore.js.
 * Anything only one module uses stays a `const` at the top of that module.
 *
 * Units are in the field names: `Px` screen pixels, `S` seconds, `Fraction`
 * a 0..1 multiple of some other length, `Ratio` a multiple of a radius,
 * `Alpha` a 0..1 opacity, `Zoom` a `cam.z` value, `Span` a width in zoom
 * units. A speed is radians per time unit (`t`, which the animation loop
 * advances by CAMERA.frameStepS per frame). Every object is frozen: they are
 * module-scope singletons read on every animation frame, never per-frame
 * allocations.
 */

/* ── Shared by both views ── */

// One dashed-stroke pattern, in the [on, off] pixel pairs ctx.setLineDash
// wants. Written as a named pair so the two numbers cannot be read the
// wrong way round, and frozen once at module load: a dash array is handed
// to the context on every frame that draws its shape.
const dash = ({ onPx, offPx }) => Object.freeze([onPx, offPx]);

/** Below this an element is invisible, so the draw is skipped entirely. */
export const MIN_VISIBLE_ALPHA = 0.01;

/** Opacity of a node's own name, in both views. */
export const LABEL_ALPHA = 0.6;

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
  // Where the mid colour stop sits between centre and edge, and how much of
  // the centre alpha a folder nebula keeps at that stop.
  midStopOffset: 0.5,
  midAlphaFraction: 0.5,
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

/** The dashed ring marking the keyboard-focused node (a11y, #675). */
export const FOCUS_RING = Object.freeze({ padPx: 4, alpha: 0.9 });
/** Its dash pattern, in [on, off] screen pixels. */
export const FOCUS_RING_DASH = dash({ onPx: 5, offPx: 4 });

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

/* ── GalaxyView: dimension stars, constellations, principle planets ── */

/** A star or cluster outside the focused constellation never fades past this. */
export const UNFOCUSED_CLUSTER_MIN_ALPHA = 0.08;

/**
 * Zoom units over which the dimension level hands over to the principle
 * level: both halves of the crossfade run on this one span, the dimension's
 * decorations fading out across it and the principle planets fading in.
 */
export const DIM_FADE_SPAN = 3;

/**
 * Constellation furniture: the dashed ring around a cluster of related
 * dimensions, the lines between its stars, and its label above the ring.
 */
export const CONSTELLATION = Object.freeze({
  // Past this zoom the whole cluster layer is gone, so it is not drawn.
  hideAtZoom: 3,
  ringAlpha: 0.15,
  lineAlpha: 0.4,
  lineWidthPx: 0.8,
  labelFontPx: 14,
  labelAlpha: 0.55,
});
/** The ring's and the lines' dash patterns, in [on, off] screen pixels. */
export const CONSTELLATION_RING_DASH = dash({ onPx: 8, offPx: 14 });
export const CONSTELLATION_LINE_DASH = dash({ onPx: 3, offPx: 5 });

/**
 * The dot that stands in for a principle while the camera is still at
 * dimension level: it orbits its star, breathes, paints a soft halo, and
 * disappears once the zoom makes it too small to be worth a draw.
 */
export const DIM_PARTICLE = Object.freeze({
  twinkleBase: 0.5,
  twinkleAmp: 0.08,
  twinkleSpeed: 0.6,
  minSizePx: 0.3,
  haloRatio: 2.5,
  haloAlpha: 0.08,
  coreAlphaBoost: 0.15,
});

/**
 * A dimension star's name, score and hit target. Font sizes are multiplied
 * by the label scale (the zoom, capped) and then floored, so a label stays
 * legible zoomed out without ballooning zoomed in.
 */
export const DIM_LABEL = Object.freeze({
  fontPx: 14,
  fontMinPx: 11,
  offsetPx: 24,
  scoreFontPx: 12,
  scoreFontMinPx: 9,
  scoreAlpha: 0.8,
  hitRadiusMinPx: 20,
});

/**
 * Principle planets: their size, the orbit ring and link line back to their
 * dimension star, the particles the unselected ones keep, and their labels.
 *
 * The unselected planets shrink their particles but keep the orbit wide, so
 * the particles do not collide with the planet: `siblingScaleCap` caps that
 * shrink, computed against the scale the planet had at `siblingReferenceZoom`.
 */
export const PRINCIPLE = Object.freeze({
  scaleFraction: 0.12,
  orbitRingAlpha: 0.1,
  linkAlpha: 0.04, linkWidthPx: 0.8,
  siblingScaleCap: 0.8,
  siblingReferenceZoom: 5,
  // Guards the divide when the planet scale is still ~0.
  scaleDivisorFloor: 0.01,
  selectedParticleScale: 0.8,
  siblingOrbitScaleMin: 0.5,
  labelFontPx: 14, labelOffsetPx: 10,
  scoreFontPx: 12,
  scoreAlpha: 0.7,
  scoreOffsetPx: 16,
  hitPadPx: 10,
  // Below this the planet is too faint to be worth hit-testing.
  hitMinAlpha: 0.4,
});

/* ── GalaxyFolderView: folder clusters and file stars ── */

/**
 * A folder star's nebula and its dashed cluster border. Zoomed out the
 * nebula is a fixed multiple of the star; zoomed past `zoomedAtZoom` it
 * tracks the camera instead and brightens over `alphaRampSpan` zoom units.
 */
export const FOLDER_NEBULA = Object.freeze({
  zoomedAtZoom: 2,
  // A fly-into this folder fades its nebula out over this much of the fly.
  flyFadeOutBy: 0.35,
  zoomedPadPx: 40,
  zoomedRadiusFraction: 0.4,
  restRadiusRatio: 5,
  alphaRampSpan: 3,
  zoomedMaxAlpha: 0.35,
  restAlpha: 0.08,
  blobAlphaRampSpan: 15,
  blobMaxAlpha: 0.18,
  blobRestAlpha: 0.025,
  borderRadiusRatio: 3.5,
  borderAlpha: 0.1,
  innerRingRadiusRatio: 2.2,
  innerRingAlpha: 0.12,
});
/** The cluster border's dash pattern, in [on, off] screen pixels. */
export const FOLDER_NEBULA_DASH = dash({ onPx: 6, offPx: 12 });

/**
 * A folder or file star itself: its particles, its violation orbs, its hit
 * target, and the dimming that keeps a big folder star from washing out the
 * scene as the camera zooms into it.
 */
export const FOLDER_STAR = Object.freeze({
  particleScaleFraction: 0.5,
  // File violation orbs only appear past this zoom, and only once drawn big
  // enough to read as an orb rather than as a speck.
  orbZoomThreshold: 2.5,
  orbMinRadiusPx: 1.5,
  hitRadiusMinPx: 14,
  // A folder star wider than this fades out over the next dimFadeSpanPx.
  dimAboveRadiusPx: 30,
  dimFadeSpanPx: 80,
  dimMinAlpha: 0.15,
});

/**
 * A folder or file star's label, its violation/compliance sub-line, and the
 * box used to keep labels from overlapping each other.
 */
export const FOLDER_LABEL = Object.freeze({
  // The label scale is the zoom capped here, so labels stop growing.
  scaleCap: 1.5,
  fontPx: 11,
  fontMinPx: 9,
  offsetPx: 14,
  // Estimated glyph width as a fraction of the font size, for the box.
  charWidthFraction: 0.55,
  heightPadPx: 4,
  collisionPadXPx: 4,
  subFontPx: 9,
  subFontMinPx: 7,
  subOffsetPx: 12,
  subLineAlpha: 0.6, rateAlpha: 0.5, // the rate reads quieter than the count
});
