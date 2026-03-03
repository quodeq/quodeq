/**
 * reportParser.js — Pure parsing layer for CodeCompass report data.
 * No Express dependency. Reads from filesystem and returns structured objects.
 */

import fsSync from 'node:fs';
import nodePath from 'node:path';

// Grade scale ordering used to resolve ties in mostCommonGrade()
const NUMERIC_SCALE = ['Critical', 'Poor', 'Adequate', 'Good', 'Exemplary'];
const TEXT_SCALE = ['Insufficient', 'Developing', 'Proficient', 'Exemplary'];
const KNOWN_SEVERITIES = ['critical', 'major', 'minor'];

// ---------------------------------------------------------------------------
// Low-level filesystem helpers
// ---------------------------------------------------------------------------

function readdirSafe(dirPath, opts = {}) {
  try {
    return fsSync.readdirSync(dirPath, opts);
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// Numeric score / grade utilities
// ---------------------------------------------------------------------------

/**
 * Convert a score string like "7.5/10" or "7.5" to a grade word.
 * Mirrors scoreUtils.scoreToGrade but kept local so this file has no imports
 * from adjacent modules at runtime (the parsers/ layer must be standalone).
 */
function gradeFromScore(scoreText) {
  if (!scoreText) return null;
  const hit = String(scoreText).match(/(\d+(?:\.\d+)?)/);
  if (!hit) return null;
  const n = parseFloat(hit[1]);
  if (n >= 9) return 'Exemplary';
  if (n >= 7) return 'Good';
  if (n >= 5) return 'Adequate';
  if (n >= 3) return 'Poor';
  return 'Critical';
}

/**
 * Extract the leading numeric value from a score string ("7.5/10" → 7.5).
 */
function numericScore(scoreText) {
  if (!scoreText) return null;
  const hit = String(scoreText).match(/(\d+(?:\.\d+)?)(?:\s*\/\s*10)?/);
  return hit ? Number(hit[1]) : null;
}

/**
 * Given an array of grade strings, return the most common one.
 * Ties are broken by which grade sits higher on the appropriate scale.
 */
function mostCommonGrade(grades) {
  if (grades.length === 0) return null;

  const tally = new Map();
  for (const g of grades) {
    tally.set(g, (tally.get(g) ?? 0) + 1);
  }

  let best = grades[0];
  let bestCount = tally.get(best) ?? 0;

  for (const [g, count] of tally) {
    if (count > bestCount) {
      best = g;
      bestCount = count;
      continue;
    }
    if (count === bestCount) {
      const ni = NUMERIC_SCALE.indexOf(g);
      const nw = NUMERIC_SCALE.indexOf(best);
      if (ni >= 0 && nw >= 0 && ni > nw) { best = g; continue; }

      const ti = TEXT_SCALE.indexOf(g);
      const tw = TEXT_SCALE.indexOf(best);
      if (ti >= 0 && tw >= 0 && ti > tw) { best = g; }
    }
  }

  return best;
}

// ---------------------------------------------------------------------------
// Run-ID / date helpers
// ---------------------------------------------------------------------------

/**
 * Parse the YYYYMMDD prefix of a run directory name into ISO + human label.
 */
function runIdToDate(runId) {
  const m = runId.match(/^(\d{4})(\d{2})(\d{2})/);
  if (!m) return null;
  const iso = `${m[1]}-${m[2]}-${m[3]}`;
  const dt = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(dt.getTime())) return null;
  return {
    iso,
    label: dt.toLocaleDateString('en-US', {
      month: 'short',
      day: '2-digit',
      timeZone: 'UTC'
    })
  };
}

// ---------------------------------------------------------------------------
// Markdown table parsing
// ---------------------------------------------------------------------------

function stripMarkupFromCell(raw) {
  return raw.replace(/\*\*/g, '').replace(/`/g, '').trim();
}

function splitRow(line) {
  const body = line.trim().replace(/^\|/, '').replace(/\|$/, '');
  return body.split('|').map(stripMarkupFromCell);
}

function isDivider(line) {
  return /^\s*\|?\s*[-:]+(\s*\|\s*[-:]+)+\s*\|?\s*$/.test(line);
}

/**
 * Extract lines that belong to the ## Executive Summary table.
 */
function extractSummarySection(markdown) {
  const lines = markdown.split(/\r?\n/);
  const startIdx = lines.findIndex(
    (l) => l.trim().toLowerCase() === '## executive summary'
  );
  if (startIdx < 0) return [];

  const tableLines = [];
  for (let i = startIdx + 1; i < lines.length; i++) {
    const l = lines[i];
    if (l.trim().startsWith('## ')) break;
    if (l.includes('|')) tableLines.push(l);
  }
  return tableLines;
}

/**
 * Parse the executive-summary markdown table into an array of row objects.
 */
function parseTableRows(markdown) {
  const raw = extractSummarySection(markdown).filter((l) => !isDivider(l));
  if (raw.length < 2) return [];

  const headers = splitRow(raw[0]);
  const rows = [];
  for (let i = 1; i < raw.length; i++) {
    const cells = splitRow(raw[i]);
    if (cells.length === 0) continue;
    const obj = {};
    headers.forEach((h, idx) => { obj[h] = cells[idx] ?? ''; });
    rows.push(obj);
  }
  return rows;
}

// ---------------------------------------------------------------------------
// Score/grade extraction from table rows
// ---------------------------------------------------------------------------

/**
 * The "Grade" column may contain "5.2/10 Adequate" (combined) or just "Adequate".
 * Split that apart and return { score, grade }.
 */
function splitScoreGrade(gradeCell, scoreCell) {
  let score = scoreCell || null;
  let grade = gradeCell || null;

  if (!score && grade) {
    const combined = grade.match(/^(\d+(?:\.\d+)?\/10)(?:\s+(\w+))?$/);
    if (combined) {
      score = combined[1];
      grade = combined[2] || null;
    }
  }

  if (!grade && score) {
    grade = gradeFromScore(score);
  }

  return { score, grade };
}

function extractOverall(rows) {
  const overallRow = rows.find((r) => {
    const p = r.Principle || r.principle || Object.values(r)[0] || '';
    return p.toLowerCase() === 'overall';
  });
  if (!overallRow) return { overallGrade: null, overallScore: null };

  const rawGrade = overallRow.Grade || overallRow.grade || null;
  const rawScore = overallRow.Score || overallRow.score || null;
  const { score, grade } = splitScoreGrade(rawGrade, rawScore);
  return { overallGrade: grade, overallScore: score };
}

function extractPrinciples(rows) {
  return rows
    .map((r) => {
      const name = r.Principle || r.principle || Object.values(r)[0] || '';
      const rawGrade = r.Grade || r.grade || null;
      const rawScore = r.Score || r.score || null;
      const { score, grade } = splitScoreGrade(rawGrade, rawScore);
      return { name, grade, score };
    })
    .filter((item) => item.name.toLowerCase() !== 'overall');
}

// ---------------------------------------------------------------------------
// Detailed findings parser (violations / compliance from code blocks)
// ---------------------------------------------------------------------------

function detectSeverity(text) {
  const m = String(text || '').match(/\b(critical|major|minor)\b/i);
  return m ? m[1].toLowerCase() : 'unknown';
}

/**
 * Parse "### Principle Name — Grade: Good" or "### ... - Score: 7/10".
 */
function parseSectionHeading(line) {
  const m = line.match(/^###\s+(.+?)\s+[—–-]\s+(Grade|Score):\s+(.+)$/i);
  if (!m) return null;
  const principle = stripMarkupFromCell(m[1]);
  const kind = m[2].toLowerCase();
  return {
    principle,
    grade: kind === 'grade' ? stripMarkupFromCell(m[3]) : null,
    score: kind === 'score' ? stripMarkupFromCell(m[3]) : null
  };
}

/**
 * Parse a single code-block body into a violation or compliance entry.
 */
function parseCodeBlock(entryType, principle, blockBody) {
  const lines = blockBody.split(/\r?\n/);
  const commentLines = [];
  const codeLines = [];
  let file = null;
  let lineNum = null;

  for (const rawLine of lines) {
    const trimmed = rawLine.trim();
    if (!trimmed) continue;

    const fileMeta = trimmed.match(/^\/\/\s*File:\s*(.+?):(\d+)\s*$/);
    if (fileMeta) {
      file = fileMeta[1].trim();
      lineNum = Number(fileMeta[2]);
      continue;
    }

    const commentMeta = trimmed.match(/^\/\/\s*(.+)$/);
    if (commentMeta) {
      commentLines.push(commentMeta[1].trim());
      continue;
    }

    codeLines.push(rawLine);
  }

  const reasonSource =
    entryType === 'violation'
      ? commentLines.find((c) => /^Violation:/i.test(c)) || commentLines[0] || ''
      : commentLines.find((c) => /^Good:/i.test(c)) || commentLines[0] || '';

  const reason = reasonSource.replace(/^(Violation|Good|Reason):\s*/i, '').trim() || null;
  const snippet = codeLines.join('\n').trim() || null;

  if (!file && !reason && !snippet) return null;

  const entry = { principle, file, line: lineNum, reason, snippet };
  if (entryType === 'violation') {
    entry.severity = detectSeverity(`${reason || ''} ${commentLines.join(' ')}`);
  }
  return entry;
}

/**
 * Walk through all lines of a markdown eval file and collect:
 *   - principleSummaries: { principle, grade, score }
 *   - violations: array of parsed violation entries
 *   - compliance: array of parsed compliance entries
 */
function parseDetailedFindings(markdown) {
  const lines = markdown.split(/\r?\n/);
  const principleSummaries = [];
  const violations = [];
  const compliance = [];

  let activePrinciple = null;
  let activeMode = null; // 'violation' | 'compliance' | null
  let insideBlock = false;
  let blockBuffer = [];

  function flush() {
    if (!insideBlock || !activePrinciple || !activeMode) return;
    const parsed = parseCodeBlock(activeMode, activePrinciple.principle, blockBuffer.join('\n'));
    if (!parsed) return;
    if (activeMode === 'violation') violations.push(parsed);
    else compliance.push(parsed);
  }

  for (const line of lines) {
    const trimmed = line.trim();

    const heading = parseSectionHeading(trimmed);
    if (heading) {
      activePrinciple = heading;
      principleSummaries.push(heading);
      activeMode = null;
      continue;
    }

    if (trimmed.startsWith('#### ')) {
      if (/^####\s+Violations Found/i.test(trimmed)) activeMode = 'violation';
      else if (/^####\s+Compliance Evidence/i.test(trimmed)) activeMode = 'compliance';
      else activeMode = null;
      continue;
    }

    if (trimmed.startsWith('```')) {
      if (!insideBlock) {
        insideBlock = true;
        blockBuffer = [];
      } else {
        flush();
        insideBlock = false;
        blockBuffer = [];
      }
      continue;
    }

    if (insideBlock) blockBuffer.push(line);
  }

  return { principleSummaries, violations, compliance };
}

// ---------------------------------------------------------------------------
// Individual file readers
// ---------------------------------------------------------------------------

function dimensionNameFromEvalPath(evalPath) {
  const base = nodePath.basename(evalPath);
  return base.endsWith('_eval.md') ? base.slice(0, -8) : base.replace(/\.md$/, '');
}

function dimensionNameFromEvidencePath(evidencePath) {
  const base = nodePath.basename(evidencePath);
  return base.endsWith('_evidence.json') ? base.slice(0, -14) : base.replace(/\.json$/, '');
}

function buildTotals(vios, compls) {
  const sev = { critical: 0, major: 0, minor: 0, unknown: 0 };
  for (const v of vios) {
    const k = KNOWN_SEVERITIES.includes(v.severity) ? v.severity : 'unknown';
    sev[k] += 1;
  }
  return {
    violationCount: vios.length,
    complianceCount: compls.length,
    severity: sev
  };
}

function readEvalFile(evalPath) {
  const md = fsSync.readFileSync(evalPath, 'utf8');
  const rows = parseTableRows(md);
  const { overallGrade, overallScore } = extractOverall(rows);
  const principles = extractPrinciples(rows);
  const details = parseDetailedFindings(md);

  return {
    dimension: dimensionNameFromEvalPath(evalPath),
    overallGrade,
    overallScore,
    principles,
    detailPrinciples: details.principleSummaries,
    violations: details.violations,
    compliance: details.compliance,
    totals: buildTotals(details.violations, details.compliance)
  };
}

function readReportJson(jsonPath) {
  let data;
  try {
    data = JSON.parse(fsSync.readFileSync(jsonPath, 'utf-8'));
  } catch {
    return null;
  }

  return {
    dimension: data.dimension ?? null,
    overallScore: data.overallScore ?? null,
    overallGrade: data.overallGrade ?? null,
    principles: (data.principles ?? []).map((p) => ({
      name: p.name,
      score: p.score ?? null,
      grade: p.grade ?? null
    })),
    detailPrinciples: [],
    violations: (data.violations ?? []).map((v) => ({
      principle: v.principle ?? null,
      file: v.file ?? null,
      line: v.line ?? null,
      reason: v.reason ?? null,
      severity: v.severity ?? 'minor',
      snippet: v.snippet ?? null
    })),
    compliance: (data.compliance ?? []).map((c) => ({
      principle: c.principle ?? null,
      file: c.file ?? null,
      line: c.line ?? null,
      reason: c.reason ?? null,
      snippet: c.snippet ?? null
    })),
    totals: {
      violationCount: data.totals?.violationCount ?? 0,
      complianceCount: data.totals?.complianceCount ?? 0,
      severity: {
        critical: data.totals?.severity?.critical ?? 0,
        major: data.totals?.severity?.major ?? 0,
        minor: data.totals?.severity?.minor ?? 0,
        unknown: 0
      }
    }
  };
}

function readEvidenceFile(evidencePath) {
  const dimName = dimensionNameFromEvidencePath(evidencePath);
  try {
    const data = JSON.parse(fsSync.readFileSync(evidencePath, 'utf8'));
    return {
      dimension: dimName,
      sourceFileCount: data.source_file_count ?? null,
      date: data.date ?? null,
      discipline: data.discipline ?? null,
      repository: data.repository ?? null
    };
  } catch {
    return { dimension: dimName, sourceFileCount: null, date: null, discipline: null, repository: null };
  }
}

// ---------------------------------------------------------------------------
// Run-level data aggregation
// ---------------------------------------------------------------------------

/**
 * Read all dimension data for a specific project run.
 * Prefers .json report files over raw _eval.md files when both exist.
 */
function loadRunDimensions(reportsRoot, project, runId) {
  const runDir = nodePath.join(reportsRoot, project, runId);
  const evalDir = nodePath.join(runDir, 'evaluation');
  const evidenceDir = nodePath.join(runDir, 'evidence');

  const evalEntries = readdirSafe(evalDir, { withFileTypes: true })
    .filter((e) => e.isFile() && e.name.endsWith('_eval.md'));

  const dimData = evalEntries
    .map((entry) => {
      const dimName = entry.name.slice(0, -8); // strip _eval.md
      const jsonFile = nodePath.join(evalDir, `${dimName}.json`);
      if (fsSync.existsSync(jsonFile)) {
        return readReportJson(jsonFile);
      }
      return readEvalFile(nodePath.join(evalDir, entry.name));
    })
    .filter(Boolean);

  // Build evidence map keyed by dimension name
  const evidenceMap = new Map(
    readdirSafe(evidenceDir, { withFileTypes: true })
      .filter((e) => e.isFile() && e.name.endsWith('_evidence.json'))
      .map((e) => {
        const parsed = readEvidenceFile(nodePath.join(evidenceDir, e.name));
        return [parsed.dimension, parsed];
      })
  );

  const dimensions = dimData.map((d) => ({
    ...d,
    sourceFileCount: evidenceMap.get(d.dimension)?.sourceFileCount ?? null,
    evidenceDate: evidenceMap.get(d.dimension)?.date ?? null,
    discipline: evidenceMap.get(d.dimension)?.discipline ?? null,
    repository: evidenceMap.get(d.dimension)?.repository ?? null
  }));

  dimensions.sort((a, b) => a.dimension.localeCompare(b.dimension));
  return dimensions;
}

// ---------------------------------------------------------------------------
// Summarize a set of dimensions into aggregate stats
// ---------------------------------------------------------------------------

function aggregateDimensions(dimensions) {
  const grades = dimensions.map((d) => d.overallGrade).filter(Boolean);
  const scores = dimensions
    .map((d) => numericScore(d.overallScore))
    .filter((v) => v !== null);

  const avgScore =
    scores.length > 0
      ? Number((scores.reduce((s, v) => s + v, 0) / scores.length).toFixed(1))
      : null;

  const gradeCount = new Map();
  for (const g of grades) gradeCount.set(g, (gradeCount.get(g) ?? 0) + 1);

  return {
    dimensionsCount: dimensions.length,
    overallGrade: mostCommonGrade(grades),
    numericAverage: avgScore,
    gradeBreakdown: Array.from(gradeCount.entries())
      .map(([grade, count]) => ({ grade, count }))
      .sort((a, b) => b.count - a.count || a.grade.localeCompare(b.grade))
  };
}

// ---------------------------------------------------------------------------
// Trend calculation
// ---------------------------------------------------------------------------

function scoreDirection(current, previous) {
  if (current == null || previous == null) return 'none';
  const parse = (v) => {
    if (typeof v === 'number') return v;
    if (typeof v !== 'string') return NaN;
    const m = v.match(/([\d.]+)/);
    return m ? parseFloat(m[1]) : NaN;
  };
  const c = parse(current);
  const p = parse(previous);
  if (isNaN(c) || isNaN(p)) return 'none';
  if (c > p) return 'up';
  if (c < p) return 'down';
  return 'same';
}

// ---------------------------------------------------------------------------
// Find the preceding valid run for a dimension
// ---------------------------------------------------------------------------

function precedingDimension(reportsRoot, project, beforeRunId, dimensionName) {
  const projectDir = nodePath.join(reportsRoot, project);
  if (!fsSync.existsSync(projectDir)) return null;

  const olderRuns = fsSync.readdirSync(projectDir)
    .filter((name) => /^\d{8}$/.test(name) && name < beforeRunId)
    .sort((a, b) => b.localeCompare(a));

  for (const runId of olderRuns) {
    const dims = loadRunDimensions(reportsRoot, project, runId);
    const match = dims.find((d) => d.dimension === dimensionName);
    if (match) return { runId, dimension: match };
  }
  return null;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * List all runs for a project, sorted newest-first.
 * Each entry: { runId, dateISO, dateLabel }
 */
export function listRuns(reportsRoot, project) {
  const projectDir = nodePath.join(reportsRoot, project);
  const entries = readdirSafe(projectDir, { withFileTypes: true })
    .filter((e) => e.isDirectory() && !e.name.startsWith('.'))
    .map((e) => {
      const parsed = runIdToDate(e.name);
      return {
        runId: e.name,
        dateISO: parsed?.iso ?? null,
        dateLabel: parsed?.label ?? e.name
      };
    });

  entries.sort((a, b) => {
    if (a.dateISO && b.dateISO) {
      return b.dateISO.localeCompare(a.dateISO) || b.runId.localeCompare(a.runId);
    }
    if (a.dateISO) return -1;
    if (b.dateISO) return 1;
    return b.runId.localeCompare(a.runId);
  });

  return entries;
}

/**
 * List all projects under reportsRoot.
 * Each entry: { name, runsCount, latestRunId, latestDate }
 */
export function listProjects(reportsRoot) {
  return readdirSafe(reportsRoot, { withFileTypes: true })
    .filter((e) => e.isDirectory() && !e.name.startsWith('.'))
    .map((e) => {
      const runs = listRuns(reportsRoot, e.name);
      return {
        name: e.name,
        runsCount: runs.length,
        latestRunId: runs[0]?.runId ?? null,
        latestDate: runs[0]?.dateISO ?? null
      };
    })
    .filter((p) => p.runsCount > 0)
    .sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * Build the full dashboard payload for a project/run combination.
 *
 * Returns:
 *   { project, availableRuns, selectedRun, summary, trend, dimensions,
 *     previousByDimension, stalePreviousByDimension, staleDimensions }
 */
export function buildDashboard(reportsRoot, project, run = 'latest') {
  const runs = listRuns(reportsRoot, project);
  if (runs.length === 0) throw new Error(`No runs found for project: ${project}`);

  const chosen = run === 'latest' ? runs[0] : runs.find((r) => r.runId === run);
  if (!chosen) throw new Error(`Run not found: ${run}`);

  const chosenDimensions = loadRunDimensions(reportsRoot, project, chosen.runId);
  const chosenSummary = aggregateDimensions(chosenDimensions);
  const chosenDimNames = new Set(chosenDimensions.map((d) => d.dimension));

  const chosenIdx = runs.findIndex((r) => r.runId === chosen.runId);

  // Cache to avoid re-reading same runs multiple times
  const dimCache = new Map();
  const getRunDims = (idx) => {
    if (!dimCache.has(idx)) {
      dimCache.set(idx, loadRunDimensions(reportsRoot, project, runs[idx].runId));
    }
    return dimCache.get(idx);
  };

  const SKIP = new Set(['NA', 'N/A', 'INSUFFICIENT']);
  const isSkipped = (grade) => !grade || SKIP.has(grade.toUpperCase());

  // For each dimension in the selected run: find the most recent older run where
  // that dimension had a non-NA grade (for trend arrows).
  const prevByDim = {};

  // Stale dimensions: exist in some run but not in the selected one.
  const staleDimMap = new Map();
  const nonNACountForStale = {};
  const stalePrevByDim = {};

  // Walk runs older than chosen (higher index = older in newest-first array)
  for (let i = chosenIdx + 1; i < runs.length; i++) {
    const dims = getRunDims(i);
    for (const dim of dims) {
      const gradeNA = isSkipped(dim.overallGrade);

      if (chosenDimNames.has(dim.dimension)) {
        if (!prevByDim[dim.dimension] && !gradeNA) {
          prevByDim[dim.dimension] = { ...dim, runId: runs[i].runId };
        }
      } else {
        if (!staleDimMap.has(dim.dimension)) {
          staleDimMap.set(dim.dimension, {
            ...dim,
            stale: true,
            fromRunId: runs[i].runId,
            fromDateISO: runs[i].dateISO
          });
        }
        if (!gradeNA) {
          nonNACountForStale[dim.dimension] = (nonNACountForStale[dim.dimension] || 0) + 1;
          if (nonNACountForStale[dim.dimension] === 2 && !stalePrevByDim[dim.dimension]) {
            stalePrevByDim[dim.dimension] = dim;
          }
        }
      }
    }
  }

  // Also check newer runs for stale dimensions we haven't captured yet
  for (let i = 0; i < chosenIdx; i++) {
    const dims = getRunDims(i);
    for (const dim of dims) {
      if (!chosenDimNames.has(dim.dimension) && !staleDimMap.has(dim.dimension)) {
        staleDimMap.set(dim.dimension, {
          ...dim,
          stale: true,
          fromRunId: runs[i].runId,
          fromDateISO: runs[i].dateISO
        });
      }
    }
  }

  const staleDimensions = Array.from(staleDimMap.values())
    .sort((a, b) => a.dimension.localeCompare(b.dimension));

  // Attach trend to each dimension of the selected run
  const dimensionsWithTrend = chosenDimensions.map((dim) => {
    const prev = prevByDim[dim.dimension];
    return {
      ...dim,
      trend: prev ? scoreDirection(dim.overallScore, prev.overallScore) : 'none',
      previousRunId: prev?.runId || null,
      previousScore: prev?.overallScore || null
    };
  });

  // Build trend series (one entry per run)
  const trend = runs.map((r) => {
    const dims = loadRunDimensions(reportsRoot, project, r.runId);
    const summary = aggregateDimensions(dims);
    return {
      runId: r.runId,
      dateISO: r.dateISO,
      dateLabel: r.dateLabel,
      dimensionsCount: summary.dimensionsCount,
      overallGrade: summary.overallGrade,
      numericAverage: summary.numericAverage
    };
  });

  return {
    project,
    availableRuns: runs,
    selectedRun: chosen,
    summary: {
      ...chosenSummary,
      dateISO: chosen.dateISO,
      dateLabel: chosen.dateLabel
    },
    trend,
    dimensions: dimensionsWithTrend,
    previousByDimension: prevByDim,
    stalePreviousByDimension: stalePrevByDim,
    staleDimensions
  };
}

/**
 * Accumulate dimension data across all runs up to (and including) asOfRun.
 * Returns the latest known state per dimension plus aggregate stats.
 */
export function buildAccumulatedData(reportsRoot, project, asOfRun = null) {
  const projectDir = nodePath.join(reportsRoot, project);
  if (!fsSync.existsSync(projectDir)) return null;

  let runIds = fsSync.readdirSync(projectDir)
    .filter((name) => /^\d{8}$/.test(name))
    .sort((a, b) => b.localeCompare(a)); // newest first

  if (asOfRun) {
    runIds = runIds.filter((id) => id <= asOfRun);
  }

  if (runIds.length === 0) return null;

  // Collect the latest evaluation per dimension (newest run wins).
  // Also collect the previous accumulated state (same logic, skipping the first run)
  // for a like-for-like overall delta in the trend badge.
  const latestPerDim = new Map();
  const prevLatestPerDim = new Map();
  const newestRunId = runIds[0];
  for (const runId of runIds) {
    const dims = loadRunDimensions(reportsRoot, project, runId);
    for (const dim of dims) {
      if (!latestPerDim.has(dim.dimension)) {
        latestPerDim.set(dim.dimension, { ...dim, fromRunId: runId });
      }
      if (runId !== newestRunId && !prevLatestPerDim.has(dim.dimension)) {
        prevLatestPerDim.set(dim.dimension, dim);
      }
    }
  }

  const allDims = Array.from(latestPerDim.values());

  // Attach trend to each dimension
  const dimensionsWithTrend = allDims.map((dim) => {
    const prev = precedingDimension(reportsRoot, project, dim.fromRunId, dim.dimension);
    return {
      ...dim,
      trend: prev ? scoreDirection(dim.overallScore, prev.dimension.overallScore) : 'none',
      previousRunId: prev?.runId || null,
      previousScore: prev?.dimension?.overallScore || null
    };
  });

  // Aggregate totals
  const grades = allDims.map((d) => d.overallGrade).filter(Boolean);
  const scores = allDims.map((d) => d.overallScore).filter(Boolean);

  let totalViolations = 0;
  let totalCompliance = 0;
  let critCount = 0;
  let majCount = 0;
  let minCount = 0;

  for (const dim of allDims) {
    totalViolations += dim.totals?.violationCount || 0;
    totalCompliance += dim.totals?.complianceCount || 0;
    critCount += dim.totals?.severity?.critical || 0;
    majCount += dim.totals?.severity?.major || 0;
    minCount += dim.totals?.severity?.minor || 0;
  }

  const numScores = scores.map((s) => numericScore(s)).filter((v) => v !== null);
  const avgScore = numScores.length > 0
    ? (numScores.reduce((a, b) => a + b, 0) / numScores.length).toFixed(1)
    : null;

  const prevScores = Array.from(prevLatestPerDim.values())
    .map((d) => numericScore(d.overallScore))
    .filter((v) => v !== null);
  const prevAvgScore = prevScores.length > 0
    ? (prevScores.reduce((a, b) => a + b, 0) / prevScores.length).toFixed(1)
    : null;

  return {
    project,
    dimensions: dimensionsWithTrend,
    summary: {
      overallGrade: mostCommonGrade(grades),
      numericAverage: avgScore,
      previousNumericAverage: prevAvgScore,
      totalViolations,
      totalCompliance,
      dimensionCount: dimensionsWithTrend.length,
      severity: { critical: critCount, major: majCount, minor: minCount }
    }
  };
}

// Re-export helpers consumed by other modules (evalParser, routes, etc.)
export { runIdToDate as parseRunIdDate, precedingDimension as getPreviousRunForDimension, scoreDirection as calculateTrend };
