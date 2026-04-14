/**
 * Generate a requirement ID from the standard ID, principle name, and sequence number.
 *
 * @param {string} standardId - The parent standard's ID (e.g. "my-standard").
 * @param {string} principleName - The principle name (e.g. "Error Handling").
 * @param {number} sequenceNumber - 1-based sequence within the principle.
 * @returns {string} A deterministic requirement ID like "MYST-ERR-01".
 */
const MAX_STD_PREFIX_CHARS = 4;
const MAX_PRINCIPLE_PREFIX_CHARS = 3;
const SEQ_PAD_WIDTH = 2;

export function generateRequirementId(standardId, principleName, sequenceNumber) {
  const prefix = (standardId || 'std').toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, MAX_STD_PREFIX_CHARS);
  const pPrefix = (principleName || 'P').replace(/[^a-zA-Z]/g, '').slice(0, MAX_PRINCIPLE_PREFIX_CHARS).toUpperCase();
  const seq = String(sequenceNumber).padStart(SEQ_PAD_WIDTH, '0');
  return `${prefix}-${pPrefix}-${seq}`;
}
