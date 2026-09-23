// Mirror of src/quodeq/core/run/dimensions.py:DimState. The progress
// endpoint only ever emits pending/running/done.
export const DIM_STATE = Object.freeze({ PENDING: 'pending', RUNNING: 'running', DONE: 'done', INCOMPLETE: 'incomplete' });
