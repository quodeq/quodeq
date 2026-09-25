// The finished-evaluation banner's two dismiss choices: EvaluationStatus.jsx
// passes one to onDismiss, hooks/useEvaluationLifecycle.js's
// handleEvalDismiss branches on VIEW ("jump to results"). A leaf module so the
// hook does not import the component.
export const EVAL_DISMISS_ACTION = Object.freeze({ VIEW: 'view', CLOSE: 'close' });
