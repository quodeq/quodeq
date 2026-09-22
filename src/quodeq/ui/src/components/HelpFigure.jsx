import { useThemeIsDark } from '../hooks/useThemeIsDark.js';

/**
 * Figure frame for Help content. Two modes:
 *  - Screenshot: pass srcDark / srcLight / alt. The variant matching the
 *    applied theme renders inside a fixed-ratio frame so a slow or broken
 *    image never shifts layout (broken images show the alt text).
 *  - Illustration: pass children built from theme tokens. By default the
 *    children are decorative (aria-hidden) and the visible figcaption is the
 *    description. Pass `informative` when the child already carries its own
 *    accessible name (e.g. an svg with role="img"/aria-label) that should
 *    reach the accessibility tree instead of being hidden behind the caption.
 * Never focusable: no tabIndex here (WebKit shows the UA focus ring on
 * mouse focus; see PR #687).
 */
export default function HelpFigure({ caption, srcDark, srcLight, alt, children, informative = false }) {
  const isDark = useThemeIsDark();
  const isImage = Boolean(srcDark || srcLight);

  return (
    <figure className="help-figure">
      {isImage ? (
        <div className="help-figure__frame help-figure__frame--image">
          <img
            className="help-figure__img"
            src={isDark ? srcDark : srcLight}
            alt={alt}
            loading="lazy"
          />
        </div>
      ) : (
        <div className="help-figure__frame">
          {informative ? <div>{children}</div> : <div aria-hidden="true">{children}</div>}
        </div>
      )}
      <figcaption className="help-figure__caption">{caption}</figcaption>
    </figure>
  );
}
