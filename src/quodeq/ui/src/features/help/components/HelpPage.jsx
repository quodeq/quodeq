import { useState } from 'react';

const SECTIONS = [
  { id: 'getting-started', label: 'Getting Started' },
  { id: 'providers', label: 'AI Providers' },
  { id: 'evaluations', label: 'Running Evaluations' },
  { id: 'dimensions', label: 'Quality Dimensions' },
  { id: 'violations', label: 'Navigating Violations' },
  { id: 'map', label: 'Code Map' },
  { id: 'standards', label: 'Custom Standards' },
  { id: 'settings', label: 'Settings' },
  { id: 'subprojects', label: 'Sub-projects' },
];

function SectionNav({ active, onSelect }) {
  return (
    <nav className="help-section-nav">
      {SECTIONS.map(s => (
        <button key={s.id} className={`help-section-btn${active === s.id ? ' active' : ''}`} onClick={() => onSelect(s.id)}>{s.label}</button>
      ))}
    </nav>
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
      <div className="help-callout help-callout-tip">
        <strong>Recommended model:</strong> <code>gemma3:27b</code> offers excellent quality-to-cost ratio for local analysis. It runs well on machines with 32GB+ RAM.
      </div>
      <p>To use Ollama:</p>
      <ol>
        <li>Install Ollama from <code>ollama.com</code></li>
        <li>Pull a model: <code>ollama pull gemma3:27b</code></li>
        <li>In Settings, select the <strong>Ollama</strong> provider tab</li>
        <li>Choose your model and configure the number of subagents</li>
      </ol>
      <p>Local models are <strong>free and private</strong> — your code never leaves your machine. The trade-off is slower analysis and potentially lower accuracy compared to cloud models.</p>

      <h3>Cloud Providers</h3>
      <div className="help-callout help-callout-warning">
        <strong>Watch your token usage.</strong> Cloud providers charge per token. A full evaluation of a medium codebase can use significant tokens. Monitor your usage in your provider's dashboard.
      </div>
      <p>Recommended cloud models:</p>
      <ul>
        <li><strong>Claude Sonnet</strong> (Anthropic) — best balance of speed, quality, and cost</li>
        <li><strong>GPT-4.1</strong> (OpenAI) — strong alternative, good for diverse codebases</li>
      </ul>
      <p>To configure a cloud provider:</p>
      <ol>
        <li>In Settings, select the <strong>CLI Provider</strong> tab</li>
        <li>Ensure your AI CLI (Claude Code, Codex, etc.) is installed and authenticated</li>
        <li>Select the model and power level for your evaluation</li>
      </ol>

      <h3>Power levels</h3>
      <table className="help-table">
        <thead>
          <tr><th>Level</th><th>Model tier</th><th>Speed</th><th>Depth</th></tr>
        </thead>
        <tbody>
          <tr><td>1 - Fast</td><td>Haiku / small</td><td>Fastest</td><td>Surface-level</td></tr>
          <tr><td>2 - Balanced</td><td>Sonnet / medium</td><td>Moderate</td><td>Good coverage</td></tr>
          <tr><td>3 - Thorough</td><td>Opus / large</td><td>Slowest</td><td>Deep analysis</td></tr>
        </tbody>
      </table>
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
        <li><strong>Local path:</strong> <code>/path/to/your/project</code></li>
        <li><strong>GitHub URL:</strong> <code>https://github.com/org/repo</code></li>
        <li><strong>SSH path:</strong> <code>git@github.com:org/repo.git</code></li>
      </ul>

      <h3>Evaluation options</h3>
      <ul>
        <li><strong>Dimensions:</strong> Choose which quality dimensions to evaluate (default: all six)</li>
        <li><strong>Branch:</strong> Select a specific branch to analyze</li>
        <li><strong>Scope:</strong> Narrow analysis to a subdirectory within the repository</li>
        <li><strong>Subagents:</strong> Number of parallel AI agents (more = faster, more tokens)</li>
      </ul>

      <h3>Scan types</h3>
      <div className="help-callout help-callout-info">
        <strong>Incremental scan:</strong> Only re-evaluates files that changed since the last run. Much faster for iterative development. Enable the <em>Incremental</em> toggle before starting.
      </div>
      <ul>
        <li><strong>Full scan:</strong> Evaluates the entire codebase from scratch. Use for first-time analysis or after major refactors.</li>
        <li><strong>Incremental scan:</strong> Detects changed files via git diff and only re-evaluates those. Previous findings for unchanged files are carried forward. Significantly faster and cheaper.</li>
      </ul>

      <h3>Re-evaluate</h3>
      <p>From the <strong>Evaluate</strong> tab, you can re-run an evaluation on an existing project. The new results will appear as a new run in the history, allowing you to track quality over time.</p>
    </section>
  );
}

function Dimensions() {
  return (
    <section className="help-section">
      <h2>Quality Dimensions (ISO 25010)</h2>
      <p>Quodeq evaluates code across six dimensions derived from the ISO/IEC 25010 software quality standard:</p>

      <table className="help-table">
        <thead>
          <tr><th>Dimension</th><th>Focus</th><th>Examples</th></tr>
        </thead>
        <tbody>
          <tr><td><strong>Security</strong></td><td>Vulnerabilities, authentication, data protection</td><td>SQL injection, hardcoded secrets, missing auth</td></tr>
          <tr><td><strong>Reliability</strong></td><td>Error handling, fault tolerance, recovery</td><td>Unhandled exceptions, missing retries, resource leaks</td></tr>
          <tr><td><strong>Maintainability</strong></td><td>Code clarity, modularity, testability</td><td>Long functions, duplicated code, tight coupling</td></tr>
          <tr><td><strong>Performance</strong></td><td>Efficiency, resource usage, scalability</td><td>N+1 queries, memory leaks, missing caching</td></tr>
          <tr><td><strong>Flexibility</strong></td><td>Extensibility, configurability, portability</td><td>Hardcoded values, missing interfaces, vendor lock-in</td></tr>
          <tr><td><strong>Usability</strong></td><td>API design, documentation, developer experience</td><td>Confusing APIs, missing docs, inconsistent naming</td></tr>
        </tbody>
      </table>

      <p>Each dimension is scored 0-10 and receives a letter grade (A-F). The overall score is a weighted average across all dimensions.</p>

      <h3>Creating custom dimensions</h3>
      <p>You can create your own evaluation standards in the <strong>Standards</strong> tab. Each standard defines principles and requirements that the AI evaluates against.</p>
      <div className="help-callout help-callout-tip">
        <strong>Tip:</strong> You can ask an AI agent to create custom dimensions for you based on the schema below.
      </div>

      <h3>Standard schema</h3>
      <pre className="help-code">{`{
  "id": "my-standard",
  "name": "My Custom Standard",
  "dimension": "security",
  "version": "1.0",
  "principles": [
    {
      "name": "Principle Name",
      "description": "What this principle evaluates",
      "requirements": [
        {
          "id": "MY-REQ-1",
          "text": "The specific requirement to check",
          "severity": "major"
        }
      ]
    }
  ]
}`}</pre>
      <p>To create a standard with an AI agent, provide the schema above and describe your evaluation criteria. The agent can generate a complete standard JSON that you can import in the Standards tab.</p>
    </section>
  );
}

function Violations() {
  return (
    <section className="help-section">
      <h2>Navigating Violations</h2>
      <p>The <strong>Violations</strong> tab shows all findings across your project, organized by dimension and severity.</p>

      <h3>Severity levels</h3>
      <table className="help-table">
        <thead>
          <tr><th>Severity</th><th>Impact</th><th>Action</th></tr>
        </thead>
        <tbody>
          <tr><td className="help-severity-critical">Critical</td><td>Immediate security or reliability risk</td><td>Fix immediately</td></tr>
          <tr><td className="help-severity-major">Major</td><td>Significant quality issue</td><td>Fix before release</td></tr>
          <tr><td className="help-severity-minor">Minor</td><td>Code improvement opportunity</td><td>Fix when convenient</td></tr>
          <tr><td className="help-severity-info">Info</td><td>Suggestion or best practice</td><td>Consider for future</td></tr>
        </tbody>
      </table>

      <h3>Exploring findings</h3>
      <ul>
        <li><strong>Click a dimension</strong> to see all findings for that quality area</li>
        <li><strong>Click a file</strong> to see all violations in that specific file with code context</li>
        <li><strong>Click a principle</strong> to see all violations for that evaluation rule</li>
        <li><strong>Severity cells</strong> in the grid are clickable — they filter by both dimension and severity</li>
      </ul>

      <h3>Dismissing findings</h3>
      <p>If a finding is a false positive or intentionally accepted, you can dismiss it. Dismissed findings are excluded from scoring in future runs but can be restored at any time.</p>
    </section>
  );
}

function CodeMap() {
  return (
    <section className="help-section">
      <h2>Code Map</h2>
      <p>The <strong>Map</strong> tab provides a visual representation of your codebase structure and quality.</p>

      <h3>Treemap view</h3>
      <p>Files are displayed as rectangles sized by their line count. Color indicates the severity density — red areas have more critical violations, green areas are clean.</p>
      <p>This makes it easy to spot:</p>
      <ul>
        <li><strong>Large red blocks:</strong> Big files with many issues — high-impact refactoring targets</li>
        <li><strong>Clusters of red:</strong> Entire modules that need attention</li>
        <li><strong>Green areas:</strong> Well-maintained parts of the codebase</li>
      </ul>

      <h3>Risk matrix</h3>
      <p>The risk matrix plots files by complexity (size) vs. issue density, helping you prioritize which files to fix first. Files in the top-right quadrant are both complex and problematic — tackle those first.</p>

      <p>Click any file in the map to see its detailed violations and code context.</p>
    </section>
  );
}

function Standards() {
  return (
    <section className="help-section">
      <h2>Custom Standards</h2>
      <p>The <strong>Standards</strong> tab lets you create, edit, and manage evaluation standards.</p>

      <h3>Built-in standards</h3>
      <p>Quodeq ships with standards based on ISO 25010 for each of the six dimensions. These provide comprehensive coverage out of the box.</p>

      <h3>Creating your own</h3>
      <ol>
        <li>Click <strong>New Standard</strong> in the Standards tab</li>
        <li>Define principles (evaluation categories) and requirements (specific checks)</li>
        <li>Assign severity levels to each requirement</li>
        <li>Save — your standard will be used in the next evaluation</li>
      </ol>

      <h3>Importing from library</h3>
      <p>You can import pre-built standards from the Quodeq library. Click <strong>Import</strong> and browse available standards.</p>

      <h3>Using AI to generate standards</h3>
      <p>Provide an AI agent with the JSON schema (shown in the Dimensions section) and describe what you want to evaluate. For example:</p>
      <pre className="help-code">{`"Create a Quodeq evaluation standard for
React component best practices. Include
principles for accessibility, performance,
state management, and error boundaries.
Use the following JSON schema: { ... }"`}</pre>
    </section>
  );
}

function Settings() {
  return (
    <section className="help-section">
      <h2>Settings</h2>
      <p>Configure your AI provider, models, and dashboard preferences in the <strong>Settings</strong> tab.</p>

      <h3>Provider configuration</h3>
      <ul>
        <li><strong>CLI Provider:</strong> Uses an installed AI CLI (Claude Code, Codex). Configure the power level and model.</li>
        <li><strong>Ollama:</strong> Uses a locally running Ollama instance. Select model and configure parallelism.</li>
      </ul>

      <h3>Model selection</h3>
      <p>Each power level maps to a model tier. You can override the default model for each level in Settings. Custom model names are stored locally.</p>

      <h3>Server info</h3>
      <p>The Settings tab shows the current server status including port, PID, and version. Use this to verify the dashboard is connected to the correct backend.</p>

      <h3>Theme</h3>
      <p>Choose between light and dark mode, and select a theme family for the dashboard appearance.</p>
    </section>
  );
}

function SubProjects() {
  return (
    <section className="help-section">
      <h2>Evaluating Sub-projects</h2>
      <p>Quodeq supports evaluating specific parts of a monorepo or multi-project repository.</p>

      <h3>Using scope</h3>
      <p>When starting an evaluation, use the <strong>Scope</strong> option to specify a subdirectory:</p>
      <pre className="help-code">{`Repository: /path/to/monorepo
Scope:      packages/frontend`}</pre>
      <p>This evaluates only the files within that subdirectory, producing a focused report for that sub-project.</p>

      <h3>Multiple evaluations</h3>
      <p>Run separate evaluations for each sub-project. Each appears as a distinct project in the dashboard with its own history and scores. You can compare quality across sub-projects in the <strong>Projects</strong> tab.</p>

      <h3>Project hierarchy</h3>
      <p>When you evaluate subdirectories of the same repository, Quodeq automatically detects the parent-child relationship and groups them in the project list.</p>
    </section>
  );
}

const SECTION_COMPONENTS = {
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
  const [activeSection, setActiveSection] = useState('getting-started');
  const Section = SECTION_COMPONENTS[activeSection] || GettingStarted;

  return (
    <div className="help-page">
      <div className="page-header">
        <h1 className="page-title">Help</h1>
        <p className="page-subtitle">Learn how to use Quodeq to evaluate and improve your code quality</p>
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
