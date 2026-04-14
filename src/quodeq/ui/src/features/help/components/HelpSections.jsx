const ICON_EYE_ON = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ verticalAlign: 'middle', marginBottom: 2 }}>
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);

export function Dimensions() {
  return (
    <section className="help-section">
      <h2>Quality Dimensions (ISO 25010)</h2>
      <p>Quodeq evaluates code across six dimensions derived from the ISO/IEC 25010 software quality standard.</p>

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

      <h3>Quodeq Dimensions</h3>
      <p>In addition to the six ISO dimensions, Quodeq includes two extra dimensions focused on software architecture:</p>
      <table className="help-table">
        <thead>
          <tr><th>Dimension</th><th>Focus</th></tr>
        </thead>
        <tbody>
          <tr><td><strong>Clean Architecture</strong></td><td>Layer separation, dependency rules, import direction, boundary enforcement</td></tr>
          <tr><td><strong>DDD Design</strong></td><td>Domain modeling, bounded contexts, aggregates, value objects, ubiquitous language</td></tr>
        </tbody>
      </table>
      <div className="help-callout help-callout-info">
        These dimensions come <strong>disabled by default</strong>. To enable them, go to the <strong>Standards</strong> tab and click the {ICON_EYE_ON} eye icon on the dimension card. Enabled dimensions will appear in the Evaluation and Overview tabs.
      </div>

      <h3>Showing and hiding dimensions</h3>
      <p>Control which dimensions are included in evaluations and displayed in the Overview using the {ICON_EYE_ON} <strong>visibility toggle</strong> on each standard card in the Standards tab:</p>
      <ul>
        <li>{ICON_EYE_ON} <strong>Eye open</strong> the dimension is active and will be included in evaluations and the Overview</li>
        <li><strong>Eye closed</strong> the dimension is hidden from evaluations and the Overview</li>
      </ul>
      <p>This lets you customize which quality aspects matter for your project without deleting any standards.</p>

      <h3>Creating custom dimensions</h3>
      <p>You can create your own evaluation standards in the <strong>Standards</strong> tab. Each standard defines principles and requirements that the AI evaluates against. See the <strong>Custom Standards</strong> section for the full schema and instructions, including how to use an AI agent to generate standards for you.</p>
    </section>
  );
}

export function Violations() {
  return (
    <section className="help-section">
      <h2>Violations</h2>
      <p>The <strong>Violations</strong> tab is where you review, explore, and manage all findings from your evaluations.</p>

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

      <h3>Navigating findings</h3>
      <ul>
        <li><strong>Click a dimension</strong> to see all findings for that quality area</li>
        <li><strong>Click a file</strong> to see all violations in that specific file with code context</li>
        <li><strong>Click a principle</strong> to see all violations for that evaluation rule</li>
        <li><strong>Severity cells</strong> in the grid are clickable and filter by both dimension and severity</li>
      </ul>

      <h3>Viewing dimensions and code</h3>
      <p>From any violation, you can drill into its dimension to see the full picture: all principles, their scores, and every finding with the relevant code snippet. This helps you understand the context around a violation and decide whether to fix it, dismiss it, or accept the trade-off.</p>

      <h3>Dismissing findings</h3>
      <p>If a finding is a false positive or intentionally accepted, you can dismiss it directly from the violation detail view. Dismissed findings:</p>
      <ul>
        <li>Are moved to the <strong>Dismissed</strong> sub-tab in the Violations view</li>
        <li>Are <strong>excluded from scoring</strong>. The dimension score updates immediately after dismissal</li>
        <li>Are <strong>excluded from future evaluations</strong>. Re-running the evaluation will not report dismissed findings again</li>
        <li>Can be <strong>restored at any time</strong> from the Dismissed tab, which brings them back into the active results</li>
      </ul>
      <p>Use this to filter out noise and focus on the violations that matter to your team. You can also use <strong>Restore All</strong> to bring back all dismissed findings at once.</p>
    </section>
  );
}

export function CodeMap() {
  return (
    <section className="help-section">
      <h2>Code Map</h2>
      <p>The <strong>Map</strong> tab provides a visual representation of your codebase structure and quality.</p>

      <h3>Treemap view</h3>
      <p>Files are displayed as rectangles sized by their line count. Color indicates severity density: red areas have more critical violations, green areas are clean.</p>
      <p>This makes it easy to spot:</p>
      <ul>
        <li><strong>Large red blocks</strong> big files with many issues, high-impact refactoring targets</li>
        <li><strong>Clusters of red</strong> entire modules that need attention</li>
        <li><strong>Green areas</strong> well-maintained parts of the codebase</li>
      </ul>

      <h3>Risk matrix</h3>
      <p>The risk matrix plots files by complexity (size) vs. issue density, helping you prioritize which files to fix first. Files in the top-right quadrant are both complex and problematic. Tackle those first.</p>

      <p>Click any file in the map to see its detailed violations and code context.</p>
    </section>
  );
}

export function Standards() {
  return (
    <section className="help-section">
      <h2>Custom Standards</h2>
      <p>The <strong>Standards</strong> tab lets you create, edit, and manage evaluation standards. Define what quality means for your project.</p>

      <h3>Built-in standards</h3>
      <p>Quodeq ships with standards based on ISO 25010 for each of the six dimensions, plus Clean Architecture and DDD Design. These provide comprehensive coverage out of the box.</p>

      <h3>Creating your own</h3>
      <ol>
        <li>Click <strong>New Standard</strong> in the Standards tab</li>
        <li>Define principles (evaluation categories) and requirements (specific checks)</li>
        <li>Assign severity levels to each requirement (<code>critical</code>, <code>major</code>, or <code>minor</code>)</li>
        <li>Save and your standard will be used in the next evaluation</li>
      </ol>

      <h3>Importing from library</h3>
      <p>You can import pre-built standards from the Quodeq library. Click <strong>Import</strong> and browse available standards.</p>

      <h3>Standard schema</h3>
      <p>Every standard follows this JSON structure:</p>
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
      <p>Key fields:</p>
      <ul>
        <li><strong>id</strong> unique identifier, used as filename (<code>my-standard.json</code>)</li>
        <li><strong>dimension</strong> the quality dimension this standard belongs to</li>
        <li><strong>principles</strong> categories of evaluation (e.g., "Error Handling", "Input Validation")</li>
        <li><strong>requirements</strong> specific checks within each principle, each with an ID and severity</li>
      </ul>

      <h3>Using AI to generate standards</h3>
      <div className="help-callout help-callout-tip">
        <strong>Tip:</strong> You can ask any AI (Claude, ChatGPT, Gemini, etc.) to generate a custom standard for you. Just ask it to produce a <code>.json</code> file following the schema above, then import it into Quodeq.
      </div>
      <p>Ask the AI something like:</p>
      <pre className="help-code">{`Generate a .quodeq JSON file for evaluating React component
best practices. Include principles for accessibility,
performance, state management, and error boundaries.

Use this structure:
{
  "id": "react-best-practices",
  "name": "React Best Practices",
  "dimension": "react",
  "principles": [
    {
      "id": "P-REACT-A11Y",
      "name": "Accessibility",
      "requirements": [
        { "id": "R-A11Y-1", "rule": "...", "severity": "major" }
      ]
    }
  ]
}`}</pre>
      <p>The AI will generate a complete standard JSON file. Save it as a <code>.json</code> file (the <code>.quodeq</code> extension is optional &mdash; it's a regular JSON file), then click the <strong>Import</strong> button in the <strong>Standards</strong> tab to load it into Quodeq.</p>
    </section>
  );
}

export function Settings() {
  return (
    <section className="help-section">
      <h2>Settings</h2>
      <p>Configure your AI provider, models, and dashboard preferences in the <strong>Settings</strong> tab.</p>

      <h3>Provider configuration</h3>
      <ul>
        <li><strong>CLI Provider</strong> uses an installed AI CLI (Claude Code, Codex). Configure the power level and model.</li>
        <li><strong>Ollama</strong> uses a locally running Ollama instance. Select a model and configure parallelism.</li>
      </ul>

      <h3>Model selection</h3>
      <p>Each power level maps to a model tier. You can override the default model for each level in Settings. Custom model names are stored locally.</p>

      <h3>Server info</h3>
      <p>The Settings tab shows the current server status including port and version. Use this to verify the dashboard is connected to the correct backend.</p>

      <h3>Theme</h3>
      <p>Choose between light and dark mode, and select a theme family for the dashboard appearance.</p>
    </section>
  );
}

export function SubProjects() {
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
