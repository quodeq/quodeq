// The Violations page's own sub-tab route param: which view of the
// violations list is showing. Not a NAV_TAB member (a page-local concept,
// not a nav-stack page). Lives here, not on ViolationsPage.jsx, since that
// component is lazy-loaded (routes/violationsRoute.jsx) and the route's own
// default-param logic needs this value without pulling in the lazy chunk.
export const VIOLATIONS_SUB_TAB = Object.freeze({ DIMENSION: 'dimension', FILE: 'file', DISMISSED: 'dismissed' });
