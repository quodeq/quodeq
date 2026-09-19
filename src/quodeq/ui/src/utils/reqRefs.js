/**
 * Keep only the requirement references that carry a linkable http(s) url.
 *
 * Findings arrive with `reqRefs` entries that may be label-only (no url) or
 * carry a non-web scheme; rendering those as anchors produces dead links, so
 * every `reqRefs` consumer filters through here.
 *
 * @param {Array<{url?: string, label?: string}>} [refs] Raw refs off a finding.
 * @returns {Array<{url?: string, label?: string}>} Refs with an http(s) url.
 */
export function filterValidRefs(refs) {
  return (refs || []).filter((r) => r?.url && /^https?:\/\//.test(r.url));
}
