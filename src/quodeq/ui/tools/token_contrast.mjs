/**
 * Token contrast audit — WCAG contrast of the text tokens against the
 * surface tokens for EVERY shipped theme combination (5 families x 2 modes).
 *
 * The UX audit's headline finding was that only the default pair ever gets
 * eyeballed while ten combinations ship; this makes the other eight fail in
 * CI instead of in a user's screenshot. Pure functions over the tokens.css
 * source text — no browser, no CSS engine. The parser (tools/_token_utils.mjs,
 * shared with token_distinctness.mjs) understands exactly the shapes
 * tokens.css uses (custom props, var() chains, hex/rgb colours, one level of
 * @media nesting); anything fancier (color-mix) is skipped.
 *
 * Run directly for the full matrix:  node tools/token_contrast.mjs
 */
import { readFileSync } from 'node:fs';
import {
  SURFACE_TOKENS, contrastRatio, defaultTokensPath, isDirectInvocation, parseBlocks, parseColor,
  printAudit, resolveVar, themeContexts,
} from './_token_utils.mjs';

export {
  SURFACE_TOKENS, contrastRatio, defaultTokensPath, parseBlocks, parseColor, resolveVar, themeContexts,
};

// Text tokens audited, with the minimum ratio each must hit against every
// surface it can sit on. --color-text and --color-text-muted carry real
// copy (body, labels, secondary text) -> WCAG AA normal-text 4.5. subtle is
// pinned at 3.0: it is documented for decorative/tertiary use, but it still
// ends up on timestamps and captions, so it must at least clear the
// large-text/UI-component floor.
export const TEXT_REQUIREMENTS = {
  '--color-text': 4.5,
  '--color-text-muted': 4.5,
  '--color-text-subtle': 3.0,
};

/**
 * @returns {{results: Array, failures: Array}} one result per
 *   theme x text-token x surface-token with the measured ratio; failures is
 *   the subset under its required minimum.
 */
export function auditContrast(cssText) {
  const blocks = parseBlocks(cssText);
  const themes = themeContexts(blocks);
  const results = [];
  for (const [theme, vars] of Object.entries(themes)) {
    for (const [textToken, min] of Object.entries(TEXT_REQUIREMENTS)) {
      const fg = parseColor(resolveVar(vars, textToken));
      if (!fg) continue;
      for (const surfaceToken of SURFACE_TOKENS) {
        const bg = parseColor(resolveVar(vars, surfaceToken));
        if (!bg) continue;
        const ratio = Math.round(contrastRatio(fg, bg) * 100) / 100;
        results.push({
          theme, textToken, surfaceToken, min, ratio,
          fg: resolveVar(vars, textToken), bg: resolveVar(vars, surfaceToken),
          ok: ratio >= min,
        });
      }
    }
  }
  return { results, failures: results.filter((r) => !r.ok) };
}

if (isDirectInvocation(import.meta.url)) {
  printAudit(
    auditContrast(readFileSync(defaultTokensPath(), 'utf8')),
    (r) => `${r.theme.padEnd(22)} ${r.textToken.padEnd(22)} on ${r.surfaceToken.padEnd(20)} ${String(r.ratio).padEnd(6)} (min ${r.min})  ${r.fg} / ${r.bg}`,
  );
}
