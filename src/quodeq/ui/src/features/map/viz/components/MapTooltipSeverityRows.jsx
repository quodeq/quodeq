import { t } from '../../../../strings/index.js';

function SeverityRow({ label, count, color }) {
  if (!(count > 0)) return null;
  return <div className="map-tooltip-row" style={{ color }}><span>{label}</span><span>{count}</span></div>;
}

/**
 * The critical, major and minor rows of a map tooltip, each in its severity
 * colour and shown only when its count is above zero.
 *
 * @param {{severity?: {critical?: number, major?: number, minor?: number}|null}} props
 */
export default function MapTooltipSeverityRows({ severity }) {
  const sev = severity || {};
  return (
    <>
      <SeverityRow label={t('map.critical')} count={sev.critical} color="var(--color-sev-critical-text)" />
      <SeverityRow label={t('map.major')} count={sev.major} color="var(--color-sev-major-text)" />
      <SeverityRow label={t('map.minor')} count={sev.minor} color="var(--color-sev-minor-text)" />
    </>
  );
}
