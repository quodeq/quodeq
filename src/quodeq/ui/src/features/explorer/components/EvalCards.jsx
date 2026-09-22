import { useRef } from 'react';
import { parseFileRef } from '../../../utils/formatters.js';
import { staggerDelayStyle } from '../../../utils/animation.js';
import FileCopyBtn from '../../../components/FileCopyBtn.jsx';
import ContextBlock from '../../../components/ContextBlock.jsx';
import { RefLinks } from '../../../components/findingDetail.jsx';
import SevBadge from '../../../components/terminal/SevBadge.jsx';
import usePretextHeight from '../../../hooks/usePretextHeight.js';
import { ViolationActions } from './violationActions.jsx';
import { t } from '../../../strings/index.js';

const ANIM_DELAY_PER_ITEM_MS = 30;
const ANIM_MAX_DELAY_MS = 300;
// Line heights pretext measures with. They mirror the rendered line height of
// `.vlive-detail--terminal .vlive-detail-title` / `.vlive-detail-reason`
// (terminal.css); a font change there must be reflected here.
const TITLE_LINE_HEIGHT_PX = 18;
const REASON_LINE_HEIGHT_PX = 20;

// Not a hook: it calls none. The file reference a card shows (`name:12-14`)
// and the one it copies (`dir/name:12-14`), derived from one raw ref.
function fileInfo(file, fileLine, fileEndLine) {
  const { filePath, line } = parseFileRef(file, fileLine);
  const filename = filePath ? filePath.split('/').pop() : null;
  const range = (fileEndLine && fileEndLine !== line) ? `${line}-${fileEndLine}` : line;
  const ref = line != null ? `${filePath}:${range}` : filePath;
  const display = line != null ? `${filename}:${range}` : filename;
  return { filePath, filename, ref, display };
}

function ViolationDetail({ item }) {
  // Measure the wrap-sensitive REASON title and DETAIL paragraph off-DOM via
  // pretext so heights are stable across resizes and so a future virtualiser
  // can query them without paint. The measured paragraph is set as
  // `min-height` on the element to reserve space before layout.
  const titleRef = useRef(null);
  const reasonRef = useRef(null);
  const titleMeasure = usePretextHeight(titleRef, item.title, { lineHeight: TITLE_LINE_HEIGHT_PX });
  const reasonMeasure = usePretextHeight(reasonRef, item.reason, { lineHeight: REASON_LINE_HEIGHT_PX });

  return (
    <div className="vlive-detail vlive-detail--terminal">
      {(item.title || item.reason || item.findings) && (
        <div className="vlive-detail-section">
          <div className="vlive-detail-section-header">
            {item.title && <span className="vlive-detail-section-label">{t('explorer.reasonLabelCaps')}</span>}
            <RefLinks reqRefs={item.reqRefs} />
          </div>
          {item.title && (
            <p
              ref={titleRef}
              className="vlive-detail-title"
              style={titleMeasure.height ? { minHeight: titleMeasure.height } : undefined}
              data-pretext-lines={titleMeasure.lineCount || undefined}
            >
              {item.title}
            </p>
          )}
          {item.reason && <>
            <span className="vlive-detail-section-label">{t('explorer.detailLabelCaps')}</span>
            <p
              ref={reasonRef}
              className="vlive-detail-reason"
              style={reasonMeasure.height ? { minHeight: reasonMeasure.height } : undefined}
              data-pretext-lines={reasonMeasure.lineCount || undefined}
            >
              {item.reason}
            </p>
          </>}
        </div>
      )}
      <ContextBlock context={item.context} snippet={item.snippet} scope={item.scope} line={item.line} />
    </div>
  );
}

export function EvalViolationCard({ v, principle, index, onDismiss }) {
  const { filename, ref, display } = fileInfo(v.file, v.line, v.endLine);
  return (
    <div
      className={`vdetail-row vdetail-row--terminal vdetail-row--${v.severity}`}
      style={staggerDelayStyle(index, ANIM_DELAY_PER_ITEM_MS, ANIM_MAX_DELAY_MS)}
    >
      <div className="vdetail-row-main">
        <SevBadge level={v.severity} format="long" />
        <span className="vrow-label">[{v.principle || principle}]</span>
        {filename && <FileCopyBtn display={display} copyText={ref} />}
        <ViolationActions v={v} principle={v.principle || principle} onDismiss={onDismiss} />
      </div>
      <ViolationDetail item={v} />
    </div>
  );
}

export function ComplianceCard({ c, principle, index }) {
  const { filename, ref, display } = fileInfo(c.file, c.line, c.endLine);
  return (
    <div
      className="vdetail-row vdetail-row--terminal vdetail-row--compliant"
      style={staggerDelayStyle(index, ANIM_DELAY_PER_ITEM_MS, ANIM_MAX_DELAY_MS)}
    >
      <div className="vdetail-row-main">
        <span className="term-sev-badge term-sev-badge--compliant">{t('explorer.compliantBadge')}</span>
        <span className="vrow-label">[{c.principle || principle}]</span>
        {filename && <FileCopyBtn display={display} copyText={ref} />}
      </div>
      <ViolationDetail item={c} />
    </div>
  );
}
