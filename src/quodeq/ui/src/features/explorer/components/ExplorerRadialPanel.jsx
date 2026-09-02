import { SectionLabel } from '../../../components/terminal/index.js';
import PrinciplesRadial from './PrinciplesRadial.jsx';
import { t } from '../../../strings/index.js';

/** The principles radial chart — the right column of the dimension page's
 * top grid. */
export default function ExplorerRadialPanel({ radialPrinciples, onPrincipleClick }) {
  return (
    <div className="qd-top-right">
      <section className="run-history-panel--terminal panel" aria-label={t('explorer.principlesRadialAria')}>
        <div className="run-history-panel__header">
          <SectionLabel>{t('explorer.principlesRadialLabel')} · {radialPrinciples.length}</SectionLabel>
          <span className="run-history-panel__stats">{t('explorer.scale010')}</span>
        </div>
        <div className="qd-radial">
          <PrinciplesRadial
            principles={radialPrinciples}
            onPrincipleClick={onPrincipleClick}
          />
        </div>
      </section>
    </div>
  );
}
