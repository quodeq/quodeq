// FNV-1a 32-bit hash, mirror of _fnv1a32 in src/quodeq/verifier/service.py.
// The round-trip identity with the Python backend is the contract that lets
// the UI compute the same finding_id the verifier persists.
export function fnv1a32(str) {
  let hash = 0x811c9dc5; // FNV offset basis
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193); // FNV prime
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

// Compute the stable composite id for a finding that has no explicit `id`.
// Real evaluation output uses this same `file|line|title` composition.
export function computeFindingId(v) {
  const file = v.file || '';
  const line = v.line ?? 0;
  const title = v.title || '';
  return fnv1a32(`${file}|${line}|${title}`);
}
