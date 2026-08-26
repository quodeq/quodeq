// Warm the lazy chunks the boot path is guaranteed to need, while the
// startup loader is still up. Boot lands on the Overview, and its
// score-history chart (recharts) is the heaviest chunk in the app: warming
// it only at DashboardPage mount measured too late — the loader could drop
// on data-ready with the chunk still in flight, showing the chart
// placeholder through the loader's fade-out. Called from App's mount
// effect; dynamic import() dedupes, so later lazy() resolutions are hits.
export function warmOverviewChunks() {
  return Promise.allSettled([
    import('./features/dashboard/components/DashboardPage.jsx'),
    import('./features/dashboard/components/RunHistoryPanel.jsx'),
  ]);
}
