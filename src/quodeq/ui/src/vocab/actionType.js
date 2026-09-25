// Assistant action-spec ids (assistant/tools/actions.py's _ACTION_SPECS keys
// / ActionSpec.action_type), the wire value on an action draft frame and the
// applied-action event. Not a Python enum on the backend (registered as
// string dict keys), so this is the UI's own closed set mirroring it.
export const ACTION_TYPE = Object.freeze({ DISMISS_FINDING: 'dismiss_finding', VERIFY_FINDING: 'verify_finding' });
