import fs from 'node:fs';
import path from 'node:path';

// ---------------------------------------------------------------------------
// Grade derivation from a numeric score string like "7/10" or "7.5"
// ---------------------------------------------------------------------------
function deriveGrade(scoreText) {
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

// ---------------------------------------------------------------------------
// Code-block extractor — returns plain text of each fenced block
// ---------------------------------------------------------------------------
function pullCodeBlocks(text) {
  const out = [];
  const re = /```[\s\S]*?```/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    out.push(m[0].replace(/```/g, '').trim());
  }
  return out;
}

// ---------------------------------------------------------------------------
// Violation-block extractor — enriches each block with severity + file ref
// ---------------------------------------------------------------------------
function pullViolationBlocks(text) {
  const out = [];
  const re = /```[\s\S]*?```/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const snippet = m[0].replace(/^```\w*\n?|```$/gm, '').trim();

    const before = text.slice(Math.max(0, m.index - 150), m.index);
    const after  = text.slice(m.index, Math.min(text.length, m.index + m[0].length + 50));
    const ctx    = before + snippet + after;

    let severity = 'minor';
    if (/critical/i.test(ctx)) severity = 'critical';
    else if (/major/i.test(ctx)) severity = 'major';

    const fileHit = snippet.match(/(?:\/\/\s*)?(?:File|@|path)[:\s]*([^\s\n:]+(?::\d+)?)/i);
    out.push({ code: snippet, severity, file: fileHit ? fileHit[1] : null });
  }
  return out;
}

// ---------------------------------------------------------------------------
// Metrics block parser
// ---------------------------------------------------------------------------
function readMetrics(section) {
  const result = {
    instancesExamined: null,
    compliantInstances: null,
    violations: null,
    complianceRate: null,
    confidenceLevel: null,
    severity: { critical: 0, major: 0, minor: 0 },
  };

  const hit = section.match(/#### Metrics([\s\S]*?)(?=#### |$)/);
  if (!hit) return result;
  const t = hit[1];

  const examined = t.match(/(\d+)\s*instances?\s*examined/i);
  if (examined) result.instancesExamined = parseInt(examined[1]);

  const compliant = t.match(/(\d+)\s*compliant/i);
  if (compliant) result.compliantInstances = parseInt(compliant[1]);

  const viols = t.match(/(\d+)\s*violations?/i);
  if (viols) result.violations = parseInt(viols[1]);

  const rate = t.match(/([\d.]+)%\s*compliance\s*rate/i);
  if (rate) result.complianceRate = parseFloat(rate[1]);

  const conf = t.match(/confidence\s*(?:level)?[:\s]*(\w+)/i);
  if (conf) result.confidenceLevel = conf[1].toLowerCase();

  const sev = t.match(/(\d+)\s*critical.*?(\d+)\s*major.*?(\d+)\s*minor/i);
  if (sev) {
    result.severity.critical = parseInt(sev[1]);
    result.severity.major    = parseInt(sev[2]);
    result.severity.minor    = parseInt(sev[3]);
  }

  return result;
}

// ---------------------------------------------------------------------------
// Priority remediation section parser
// ---------------------------------------------------------------------------
function readRemediation(content) {
  const out = { critical: [], major: [], minor: [] };

  const hit = content.match(/## Priority Remediation([\s\S]*?)(?=## |$)/i);
  if (!hit) return out;
  const text = hit[1];

  function parseItems(raw) {
    const items = [];
    for (const line of raw.split('\n').filter((l) => l.trim().match(/^[-*\d]/))) {
      const clean = line.replace(/^[-*\d.)\s]+/, '').trim();
      if (!clean) continue;
      const fref = clean.match(/`([^`]+:\d+)`|(\S+\.\w+:\d+)/);
      items.push({ description: clean, file: fref ? (fref[1] || fref[2]) : null });
    }
    return items;
  }

  const critHit = text.match(/### Critical([\s\S]*?)(?=### |$)/i);
  if (critHit) out.critical = parseItems(critHit[1]);

  const majHit = text.match(/### Major([\s\S]*?)(?=### |$)/i);
  if (majHit) out.major = parseItems(majHit[1]);

  const minHit = text.match(/### Minor([\s\S]*?)(?=### |$)/i);
  if (minHit) out.minor = parseItems(minHit[1]);

  return out;
}

// ---------------------------------------------------------------------------
// JSON report path handler
// ---------------------------------------------------------------------------
function parseFromJson(jsonPath, project, runId, dimension) {
  let data;
  try {
    data = JSON.parse(fs.readFileSync(jsonPath, 'utf-8'));
  } catch {
    return null;
  }

  const principleGrades = [
    ...(data.principles ?? []).map((p) => ({
      principle: p.name,
      score:     p.score ?? null,
      grade:     p.grade ?? null,
      isOverall: false,
    })),
    {
      principle: 'Overall',
      score:     data.overallScore ?? null,
      grade:     data.overallGrade ?? null,
      isOverall: true,
    },
  ];

  // Build per-principle detail by grouping top-level violations and compliance
  const principleMap = {};
  for (const p of data.principles ?? []) {
    principleMap[p.name] = {
      name:            p.name,
      score:           p.score ?? null,
      grade:           p.grade ?? null,
      violations:      [],
      compliance:      [],
      justification:   '',
      recommendations: [],
      metrics:         null,
    };
  }
  for (const v of data.violations ?? []) {
    const key = v.principle;
    if (!principleMap[key]) {
      principleMap[key] = { name: key, score: null, grade: null, violations: [], compliance: [], justification: '', recommendations: [], metrics: null };
    }
    principleMap[key].violations.push({
      code:     v.snippet || '',
      severity: v.severity || 'minor',
      file:     v.file ? (v.line ? `${v.file}:${v.line}` : v.file) : null,
      reason:   v.reason || '',
    });
  }
  for (const c of data.compliance ?? []) {
    const key = c.principle;
    if (!principleMap[key]) {
      principleMap[key] = { name: key, score: null, grade: null, violations: [], compliance: [], justification: '', recommendations: [], metrics: null };
    }
    principleMap[key].compliance.push(c.snippet || c.reason || '');
  }
  const principles = Object.values(principleMap);

  return {
    dimension,
    runId,
    project,
    principleGrades,
    principles,
    violations:          data.violations ?? [],
    compliance:          data.compliance ?? [],
    priorityRemediation: { critical: [], major: [], minor: [] },
    rawContent:          null,
  };
}

// ---------------------------------------------------------------------------
// Markdown report path handler
// ---------------------------------------------------------------------------
function parseFromMarkdown(mdPath, project, runId, dimension) {
  let content;
  try {
    content = fs.readFileSync(mdPath, 'utf-8');
  } catch {
    return null;
  }

  // --- Executive Summary table ---
  // Supports: | Principle | Grade |  (2-col)
  //           | Principle | Score | Grade |  (3-col)
  //           | Principle | Compliance Level | Adjustments | Grade |  (4-col)
  const summaryHit = content.match(/## Executive Summary[\s\S]*?\| Principle \|[^\n]*\|[\s\S]*?\n\n/);
  const principleGrades = [];

  if (summaryHit) {
    const tableLines = summaryHit[0]
      .split('\n')
      .filter((l) => l.startsWith('|') && !l.includes('---'));

    const headerCells = tableLines[0].split('|').map((c) => c.trim()).filter(Boolean);
    const is4Col = headerCells.length >= 4;

    for (const line of tableLines.slice(1)) {
      const cells = line.split('|').map((c) => c.trim()).filter(Boolean);
      if (cells.length < 2) continue;

      const principle = cells[0].replace(/\*\*/g, '');
      let score = null;
      let grade = null;

      if (is4Col) {
        const raw = cells[cells.length - 1].replace(/\*\*/g, '');
        const combo = raw.match(/^(\d+(?:\.\d+)?\/10)(?:\s+(\w+))?$/);
        if (combo) {
          score = combo[1];
          grade = combo[2] || null;
        } else {
          score = raw;
        }
      } else if (cells.length >= 3) {
        score = cells[1].replace(/\*\*/g, '');
        grade = cells[2].replace(/\*\*/g, '');
      } else {
        grade = cells[1].replace(/\*\*/g, '');
      }

      if (!grade && score) grade = deriveGrade(score);

      principleGrades.push({ principle, score, grade, isOverall: principle.toLowerCase().includes('overall') });
    }
  }

  // --- Detailed findings per principle ---
  const principles = [];
  const sectionRe = /### (.+?) [—–-] (?:Grade|Score): ([\w/.]+)[\s\S]*?(?=### |\n---\n|$)/g;
  let m;

  while ((m = sectionRe.exec(content)) !== null) {
    const name    = m[1].trim();
    const grade   = m[2].trim();
    const section = m[0];

    const compHit = section.match(/#### Compliance Evidence([\s\S]*?)(?=#### |$)/);
    const compliance = compHit ? pullCodeBlocks(compHit[1]) : [];

    const violHit = section.match(/#### Violations Found([\s\S]*?)(?=#### |$)/);
    const violations = violHit ? pullViolationBlocks(violHit[1]) : [];

    const findHit = section.match(/#### Findings([\s\S]*?)(?=#### |$)/);
    const findings = findHit ? findHit[1].trim() : '';

    const justHit = section.match(/#### Grade Justification([\s\S]*?)(?=#### |$)/);
    const justification = justHit ? justHit[1].trim() : '';

    const recHit = section.match(/#### Recommendations([\s\S]*?)(?=### |---|$)/);
    const recommendations = recHit
      ? recHit[1].trim().split(/\n\d+\.\s+/).filter(Boolean)
      : [];

    principles.push({
      name,
      grade,
      compliance,
      violations,
      findings,
      justification,
      recommendations,
      metrics: readMetrics(section),
    });
  }

  return {
    dimension,
    runId,
    project,
    principleGrades,
    principles,
    priorityRemediation: readRemediation(content),
    rawContent:          content,
  };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------
export function parseEvalFile(reportsRoot, project, runId, dimension) {
  const base = path.join(reportsRoot, project, runId, 'evaluation');

  const jsonPath = path.join(base, `${dimension}.json`);
  if (fs.existsSync(jsonPath)) {
    return parseFromJson(jsonPath, project, runId, dimension);
  }

  const mdPath = path.join(base, `${dimension}_eval.md`);
  if (!fs.existsSync(mdPath)) return null;

  return parseFromMarkdown(mdPath, project, runId, dimension);
}
