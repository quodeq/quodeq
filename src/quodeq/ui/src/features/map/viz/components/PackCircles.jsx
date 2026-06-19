import { nodeColor, nodeBorderColor } from '../core/mapColors.js';
import FileShape from './FileShape.jsx';

const FOLDER_STROKE_WIDTH = 1.5;
const FOLDER_FILL_OPACITY_HOVER = 0.3;
const FOLDER_FILL_OPACITY_DEFAULT = 0.2;

export default function PackCircles({ circles, folderIndices, fileIndices, hover, setHover, viewMode, k, handleClick }) {
  return (
    <>
      {folderIndices.map((i) => {
        const c = circles[i];
        const d = c.data;
        const isRoot = c.depth === 0;
        const isHovered = hover === i;
        return (
          <circle key={d.path || i} cx={c.x} cy={c.y} r={c.r}
            fill={isRoot ? 'var(--color-surface-alt)' : nodeColor(d, viewMode)}
            stroke={isRoot ? 'var(--color-border)' : nodeBorderColor(d, viewMode)}
            strokeWidth={FOLDER_STROKE_WIDTH} vectorEffect="non-scaling-stroke"
            fillOpacity={isRoot ? 1 : isHovered ? FOLDER_FILL_OPACITY_HOVER : FOLDER_FILL_OPACITY_DEFAULT}
            style={{ cursor: 'pointer', transition: 'fill-opacity 0.15s' }}
            tabIndex={0}
            role="button"
            aria-label={d.name || d.path}
            onClick={(e) => handleClick(e, c)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleClick(e, c); } }}
            onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
          />
        );
      })}
      {fileIndices.map((i) => {
        const c = circles[i];
        const d = c.data;
        return (
          <FileShape key={d.path || i} cx={c.x} cy={c.y} r={c.r}
            color={nodeColor(d, viewMode)} borderColor={nodeBorderColor(d, viewMode)}
            glow={hover === i} parentScale={k}
            handlers={{ onClick: (e) => handleClick(e, c), onMouseEnter: () => setHover(i), onMouseLeave: () => setHover(null) }}
          />
        );
      })}
    </>
  );
}
