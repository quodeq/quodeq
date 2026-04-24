import { useState } from 'react';
import { Dimensions, Violations, CodeMap, Standards, Settings, SubProjects } from './HelpSections.jsx';
import { TermHeader } from '../../../components/terminal/index.js';
import BrandCarousel from '../../../components/BrandCarousel.jsx';

const SECTIONS = [
  { id: 'philosophy', label: 'Philosophy' },
  { id: 'getting-started', label: 'Getting Started' },
  { id: 'providers', label: 'AI Providers' },
  { id: 'evaluations', label: 'Running Evaluations' },
  { id: 'dimensions', label: 'Quality Dimensions' },
  { id: 'violations', label: 'Violations' },
  { id: 'map', label: 'Code Map' },
  { id: 'standards', label: 'Custom Standards' },
  { id: 'settings', label: 'Settings' },
  { id: 'subprojects', label: 'Sub-projects' },
];

function SectionNav({ active, onSelect }) {
  return (
    <nav className="help-section-nav">
      {SECTIONS.map(s => (
        <button key={s.id} className={`help-section-btn${active === s.id ? ' active' : ''}`} onClick={() => onSelect(s.id)} aria-pressed={active === s.id}>{s.label}</button>
      ))}
    </nav>
  );
}

function Philosophy() {
  return (
    <section className="help-section">
      <h2>The Quodeq Philosophy</h2>
      <p>Quodeq is a quality compass for your codebase. Not a linter, not a static analyzer. An AI-powered evaluator that reads and understands your code the way a senior engineer would.</p>

      <h3>Why Quodeq exists</h3>
      <p>Traditional code quality tools count syntax violations. They can tell you a function is too long, but not whether your architecture has a dependency leak. They can flag a missing null check, but not whether your error handling strategy is coherent across the project.</p>
      <p>Quodeq takes a different approach. It sends an AI agent into your codebase with read-only tools to explore, understand context, and evaluate quality against structured standards. The agent reads actual code, follows imports, understands patterns, and reports what it finds with specific file locations and evidence.</p>

      <h3>How evaluation works</h3>
      <ol>
        <li><strong>Detect</strong> identifies the languages, frameworks, and structure of your codebase</li>
        <li><strong>Analyze</strong> spawns AI agents with read-only tools (Bash, Grep, Read, Glob) to systematically explore the code</li>
        <li><strong>Collect</strong> streams findings in real-time as structured JSONL via tool calls</li>
        <li><strong>Score</strong> maps findings to ISO 25010 principles with CWE classifications</li>
        <li><strong>Report</strong> produces per-dimension reports with grades, violations, and compliance evidence</li>
        <li><strong>Fix Plan</strong> for each violation, you can copy a structured fix plan with file path, line number, code context, and remediation guidance, ready to paste into your AI agent or IDE</li>
      </ol>

      <h3>Both sides of the story</h3>
      <p>Quodeq reports <strong>violations AND compliance</strong>. The scoring uses the ratio between them. A project with many violations but also strong compliance patterns is scored more fairly than one with the same violations and no evidence of good practices. The AI actively looks for files that follow standards correctly, not just files that break them.</p>

      <h3>The Q&#xB2; Scoring Formula</h3>
      <p>Each principle is scored 0 to 10 using four independent constraints that together avoid the typical pitfalls of naive scoring. A hyperbolic <strong>violation base</strong> means the first violations hurt most, preventing fifty minor issues from tanking a score the same way five critical ones would. A <strong>compliance lift</strong> fills the gap between the base and 10 with evidence of good practices, so compliance always helps and never hurts. A log-based <strong>violation ceiling</strong> prevents compliance from overriding significant violations, so you cannot reach Exemplary with critical issues in play. A <strong>severity grade floor</strong> keeps the grade label honest, so only actual critical violations can produce a "Critical" grade.</p>

      <p>Quodeq ships with ISO 25010 dimensions plus Clean Architecture and DDD standards, and evaluates any codebase in any language: Python, TypeScript, Go, Rust, Java, Swift, or anything else. You can also write your own standards for whatever quality means in your project.</p>
    </section>
  );
}

function GettingStarted() {
  return (
    <section className="help-section">
      <h2>Getting Started</h2>
      <p>Quodeq evaluates your codebase across six quality dimensions based on ISO 25010. It uses AI to analyze source code, identify violations, and score each dimension.</p>
      <h3>Quick start</h3>
      <ol>
        <li>Go to the <strong>Evaluate</strong> tab</li>
        <li>Enter a local path, GitHub URL, or SSH path to your repository</li>
        <li>Click <strong>Start Evaluation</strong></li>
        <li>Once complete, explore results in the <strong>Overview</strong>, <strong>Violations</strong>, and <strong>Map</strong> tabs</li>
      </ol>
      <h3>Requirements</h3>
      <ul>
        <li><strong>Python 3.12+</strong> and <strong>Node.js 18+</strong></li>
        <li>At least one AI provider configured (see AI Providers section)</li>
      </ul>
    </section>
  );
}

function Providers() {
  return (
    <section className="help-section">
      <h2>AI Providers</h2>
      <p>Quodeq supports multiple AI providers for analysis. Configure them in the <strong>Settings</strong> tab.</p>

      <h3>Local Providers (Ollama)</h3>
      <p><strong>Recommended model:</strong> <code>gemma4:26b</code> offers an excellent quality-to-cost ratio for local analysis. Even with context limited to 32k tokens, results are strong.</p>
      <p>To use Ollama:</p>
      <ol>
        <li>Install Ollama from <code>ollama.com</code></li>
        <li>Pull a model: <code>ollama pull gemma4:26b</code></li>
        <li>In Settings, select the <strong>Ollama</strong> provider tab</li>
        <li>Choose your model and configure the number of subagents</li>
      </ol>
      <p>Local models are <strong>free and private</strong>. Your code never leaves your machine. The trade-off is slower analysis and potentially lower accuracy compared to cloud models.</p>

      <h3>Cloud Providers</h3>
      <p>Cloud providers charge per token, so watch your usage. A full evaluation of a medium codebase can consume significant tokens, so monitor your usage in your provider's dashboard. <strong>Claude Sonnet</strong> (Anthropic) is the best balance of speed, quality, and cost; <strong>GPT-5.3-codex</strong> (OpenAI) is a strong alternative for diverse codebases.</p>
      <p>To configure a cloud provider:</p>
      <ol>
        <li>In Settings, select the <strong>CLI Provider</strong> tab</li>
        <li>Ensure your AI CLI (Claude Code, Codex, etc.) is installed and authenticated</li>
        <li>Select the model and power level for your evaluation</li>
      </ol>
      <p>Power level trades speed for depth: <strong>fast</strong>, <strong>balanced</strong>, and <strong>thorough</strong> map to small, medium, and large model tiers respectively.</p>
    </section>
  );
}

function Evaluations() {
  return (
    <section className="help-section">
      <h2>Running Evaluations</h2>
      <p>Navigate to the <strong>Evaluate</strong> tab to start an analysis.</p>

      <h3>Input types</h3>
      <ul>
        <li><strong>Local path</strong> <code>/path/to/your/project</code></li>
        <li><strong>GitHub URL</strong> <code>https://github.com/org/repo</code></li>
        <li><strong>SSH path</strong> <code>git@github.com:org/repo.git</code></li>
      </ul>

      <h3>Evaluation options</h3>
      <ul>
        <li><strong>Dimensions</strong> choose which quality dimensions to evaluate (default: all six)</li>
        <li><strong>Branch</strong> select a specific branch to analyze</li>
        <li><strong>Scope</strong> narrow analysis to a subdirectory within the repository</li>
        <li><strong>Subagents</strong> number of parallel AI agents (more agents means faster analysis but more tokens)</li>
      </ul>

      <h3>Scan types</h3>
      <ul>
        <li><strong>Full scan</strong> evaluates the entire codebase from scratch. Use for first-time analysis or after major refactors.</li>
        <li><strong>Incremental scan</strong> detects changed files via git diff and only re-evaluates those. Previous findings for unchanged files are carried forward, making it significantly faster and cheaper. Enable the <em>Incremental</em> toggle before starting.</li>
      </ul>

      <h3>Re-evaluate</h3>
      <p>From the <strong>Evaluate</strong> tab, you can re-run an evaluation on an existing project. The new results appear as a new run in the history, allowing you to track quality over time.</p>
    </section>
  );
}

const SECTION_COMPONENTS = {
  'philosophy': Philosophy,
  'getting-started': GettingStarted,
  'providers': Providers,
  'evaluations': Evaluations,
  'dimensions': Dimensions,
  'violations': Violations,
  'map': CodeMap,
  'standards': Standards,
  'settings': Settings,
  'subprojects': SubProjects,
};

export default function HelpPage() {
  const [activeSection, setActiveSection] = useState('philosophy');
  const Section = SECTION_COMPONENTS[activeSection] || Philosophy;

  return (
    <div className="help-page help-page--terminal">
      <div className="help-header">
        <TermHeader
          name="help"
          sub="learn how to use quodeq to evaluate and improve your code quality"
        />
        <BrandCarousel />
      </div>
      <div className="help-layout">
        <SectionNav active={activeSection} onSelect={setActiveSection} />
        <div className="help-content">
          <Section />
        </div>
      </div>
    </div>
  );
}
