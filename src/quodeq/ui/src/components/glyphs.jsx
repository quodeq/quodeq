/**
 * Inline glyphs drawn in more than one feature.
 *
 * Each is the same 24x24 line drawing wherever it appears; `size` sets the
 * rendered box and `square` keeps the SVG default caps and joins for the
 * places that draw the glyph without rounding.
 */
import Icon from './Icon.jsx';

// Passed to Icon to drop its rounded caps/joins (React omits a null attribute).
const SQUARE_STROKE = { strokeLinecap: null, strokeLinejoin: null };

/** Tray with a down arrow: download / export. */
export function DownloadGlyph({ size, square }) {
  return (
    <Icon size={size} {...(square ? SQUARE_STROKE : null)}>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </Icon>
  );
}

/** Lidded bin: delete. */
export function TrashGlyph({ size, square }) {
  return (
    <Icon size={size} {...(square ? SQUARE_STROKE : null)}>
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6M14 11v6" />
      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    </Icon>
  );
}
