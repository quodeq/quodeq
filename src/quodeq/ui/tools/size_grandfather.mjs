// Grandfathered size-ratchet offenders (eslint.size.config.js).
//
// Generated from files that violate max-lines (300, all files) or
// max-lines-per-function (50, non-test files only -- test files are
// exempt from that rule in eslint.size.config.js, since ESLint counts a
// describe(...) callback's body as one function, and grouping related
// test cases under a describe routinely exceeds 50 lines regardless of
// file size). Paths are relative to src/quodeq/ui, posix-separated. The
// list may only shrink: split a file, then remove its entry here
// (tools/check_size_grandfather.mjs enforces the ceiling).
export const SIZE_GRANDFATHER = [
  "src/features/assistant/useAssistantStream.js",
  "src/features/dashboard/components/DashboardPage.jsx",
  "src/features/map/viz/components/GalaxyView.jsx",
  "src/hooks/useAppState.js",
];
