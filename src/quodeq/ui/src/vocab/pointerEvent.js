// Pointer-drag DOM events every drag/resize gesture in the app watches:
// window pointermove during the gesture, pointerup to end it. Shared across
// features (side-pane's resizers, the bottom drawer, the grade-formula
// boundary bar), so it lives here rather than on one feature's hook.
export const POINTER_EVENT = Object.freeze({ MOVE: 'pointermove', UP: 'pointerup' });
