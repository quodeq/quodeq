/**
 * The per-frame camera move both galaxy canvases run.
 *
 * The galaxy view and the folder view each drive their own camera, but the
 * three cases are identical: snap for the opening frames, lerp towards the
 * target while idle, and ease along an in-flight transition. Only the
 * transition length and the idle lerp fraction differ, so they are passed in.
 *
 * Parameters are positional on purpose: this runs once per animation frame
 * and an options object would allocate on every one.
 */
import { CAMERA } from './galaxyTuning.js';
import { easeInOutCubic, easeLagged } from './galaxyEasing.js';

/**
 * Move `cam` one frame towards `tg`, in place.
 *
 * @param {{x: number, y: number, z: number}} cam Camera, mutated in place.
 * @param {{x: number, y: number, z: number}} tg Target camera pose.
 * @param {{t: number, sx: number, sy: number, sz: number, out: boolean}|null} anim
 *   In-flight transition, or null when the camera is idle.
 * @param {number} frameCount Frames drawn since the scene opened.
 * @param {number} transitionS Transition length in seconds.
 * @param {number} idleLerp Fraction of the remaining distance covered per idle frame.
 * @returns {boolean} true on the frame an in-flight transition reaches its end.
 */
export function interpolateCamera(cam, tg, anim, frameCount, transitionS, idleLerp) {
  if (!anim) {
    if (frameCount <= CAMERA.snapFrames) {
      cam.x = tg.x; cam.y = tg.y; cam.z = tg.z;
    } else {
      cam.x += (tg.x - cam.x) * idleLerp;
      cam.y += (tg.y - cam.y) * idleLerp;
      cam.z += (tg.z - cam.z) * idleLerp;
    }
    return false;
  }
  anim.t = Math.min(1, anim.t + CAMERA.frameStepS / transitionS);
  const ease = easeInOutCubic(anim.t);
  const lagE = easeLagged(anim.t);
  const posE = anim.out ? ease : lagE;
  const zoomE = anim.out ? lagE : ease;
  cam.x = anim.sx + (tg.x - anim.sx) * posE;
  cam.y = anim.sy + (tg.y - anim.sy) * posE;
  cam.z = anim.sz + (tg.z - anim.sz) * zoomE;
  return anim.t >= 1;
}
