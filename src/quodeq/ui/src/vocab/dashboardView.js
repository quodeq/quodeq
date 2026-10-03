// Mirror of src/quodeq/core/types/dashboard_view.py:DashboardView. Wire value
// (`?view=`). The UI only ever asks for `overview` (scores and counts, no
// finding lists); run pages read their lists from /scores/<run> instead
// (features/dashboard/hooks/useRunFindings.js). `full` is the server's
// default for other clients.
export const DASHBOARD_VIEW = Object.freeze({ FULL: 'full', OVERVIEW: 'overview' });
