/**
 * Generate a requirement ID from the standard ID, principle name, and sequence number.
 *
 * @param {string} standardId - The parent standard's ID (e.g. "my-standard").
 * @param {string} principleName - The principle name (e.g. "Error Handling").
 * @param {number} sequenceNumber - 1-based sequence within the principle.
 * @returns {string} A deterministic requirement ID like "MYST-ERR-01".
 */
export function generateRequirementId(standardId, principleName, sequenceNumber) {
  const prefix = (standardId || 'std').toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 4);
  const pPrefix = (principleName || 'P').replace(/[^a-zA-Z]/g, '').slice(0, 3).toUpperCase();
  const seq = String(sequenceNumber).padStart(2, '0');
  return `${prefix}-${pPrefix}-${seq}`;
}
