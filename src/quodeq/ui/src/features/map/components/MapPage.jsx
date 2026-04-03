export default function MapPage({ data }) {
  const dimensions = data?.accumulated?.dimensions || data?.dashboard?.dimensions || [];
  return (
    <div className="map-page">
      <div className="page-header">
        <h2 className="page-title">Map</h2>
        <span className="page-count">{dimensions.length} dimensions</span>
      </div>
      <p className="empty-state">Map visualizations loading...</p>
    </div>
  );
}
