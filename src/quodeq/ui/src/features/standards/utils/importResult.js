// Pure characterization of ImportModal's import flow: how a `importStandard`
// response classifies into an outcome, and how a picked file parses into
// importable data. No React, no i18n -- the hook (useImportFlow.js) maps
// these outcomes to view state and translated copy.

export const BYTES_PER_KB = 1024;
export const MAX_FILE_SIZE = BYTES_PER_KB * BYTES_PER_KB; // 1MB

export const IMPORT_OUTCOME = { SUCCESS: 'success', CONFLICT: 'conflict', WARNINGS: 'warnings' };

export const PARSE_FILE_ERROR = {
  TOO_LARGE: 'tooLarge',
  INVALID_JSON: 'invalidJson',
  INVALID_JSON_OBJECT: 'invalidJsonObject',
};

/**
 * Classifies an `importStandard(data, force)` response into the outcome
 * ImportModal renders: a conflicting existing standard (needs force to
 * overwrite), non-fatal warnings (needs "import anyway"), or success.
 *
 * `force` mirrors the caller's own force flag: warnings only gate the flow
 * when the caller hasn't already opted to force the import.
 */
export function classifyImportResult(result, force) {
  if (result?._conflict) {
    return { kind: IMPORT_OUTCOME.CONFLICT, conflict: result.existing, warnings: result.warnings || [] };
  }
  if (result?.warnings?.length > 0 && !force) {
    return { kind: IMPORT_OUTCOME.WARNINGS, warnings: result.warnings };
  }
  // The server echoes the stored standard; the caller falls back to the
  // file's own id when detail.id is absent.
  return { kind: IMPORT_OUTCOME.SUCCESS, id: result?.detail?.id };
}

/**
 * Parses a picked file into importable JSON data. Enforces the same size
 * cap and shape checks ImportModal has always applied before offering the
 * data to `importStandard`.
 */
export async function parseImportFile(file) {
  if (file.size > MAX_FILE_SIZE) {
    return { ok: false, error: PARSE_FILE_ERROR.TOO_LARGE, size: file.size };
  }
  let data;
  try {
    const text = await file.text();
    data = JSON.parse(text);
  } catch (err) {
    return { ok: false, error: PARSE_FILE_ERROR.INVALID_JSON, cause: err };
  }
  if (typeof data !== 'object' || Array.isArray(data)) {
    return { ok: false, error: PARSE_FILE_ERROR.INVALID_JSON_OBJECT };
  }
  return { ok: true, data };
}
