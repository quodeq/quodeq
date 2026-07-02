import HelpFigure from '../../../components/HelpFigure.jsx';
import GradeFormulaCurveFigure from './figures/GradeFormulaCurveFigure.jsx';
import ScoreGroupingFigure from './figures/ScoreGroupingFigure.jsx';
import gradeFormulaDark from '../../../assets/help/grade-formula.dark.webp';
import gradeFormulaLight from '../../../assets/help/grade-formula.light.webp';

const ICON_EYE_ON = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ verticalAlign: 'middle', marginBottom: 2 }}>
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);

function Tip({ title, children }) {
  return (
    <aside className="help-tip" role="note">
      {title && <div className="help-tip__title">{title}</div>}
      <div className="help-tip__body">{children}</div>
    </aside>
  );
}

function KeyTable({ rows }) {
  return (
    <div className="help-keytable" role="table">
      {rows.map(([k, v]) => (
        <div className="help-keytable__row" key={k} role="row">
          <div className="help-keytable__k" role="cell">{k}</div>
          <div className="help-keytable__v" role="cell">{v}</div>
        </div>
      ))}
    </div>
  );
}

export function Philosophy() {
  return (
    <section className="help-section">
      <h2>The Quodeq Philosophy</h2>
      <p>Quodeq is a quality compass for your codebase. Not a linter, not a static analyzer. An AI-powered evaluator that reads and understands your code the way a senior engineer would, then reports both what is wrong and what is right.</p>

      <h3>Why Quodeq exists</h3>
      <p>Traditional code-quality tools count syntax violations. They flag a long function or a missing null check, but they cannot tell you whether your architecture has a dependency leak, whether your error-handling strategy is coherent, or whether your domain model has eroded.</p>
      <p>Quodeq sends AI agents into your codebase with read-only tools to explore, follow imports, understand patterns, and evaluate quality against structured standards. Every finding cites a file, a line, a code snippet, and a principle.</p>

      <h3>How an evaluation runs</h3>
      <ol>
        <li><strong>Detect</strong> identifies languages, frameworks, and structure.</li>
        <li><strong>Analyze</strong> spawns parallel sub-agents with read-only tools (Bash, Grep, Read, Glob).</li>
        <li><strong>Collect</strong> streams structured findings (JSONL) live as the agents work.</li>
        <li><strong>Score</strong> maps findings to principles and computes per-dimension scores.</li>
        <li><strong>Report</strong> produces grades, trend deltas, and per-finding fix plans.</li>
      </ol>

      <h3>Both sides of the story</h3>
      <p>Quodeq reports <strong>violations and compliance</strong>. Scoring uses the ratio between them, so a project with many violations but strong compliance patterns scores more fairly than one with the same violations and no evidence of good practice. Agents actively look for files that follow standards correctly, not just files that break them.</p>

      <h3>The Q&#xB2; scoring formula</h3>
      <p>Each principle is scored 0 to 10 using four constraints designed to avoid the usual pitfalls of naive scoring.</p>
      <ul>
        <li>A hyperbolic <strong>violation base</strong> means the first violations hurt most. Fifty minor issues will not tank a score the way five critical ones do.</li>
        <li>A <strong>compliance lift</strong> fills the gap between the base and 10 with evidence of good practice, so compliance always helps and never hurts.</li>
        <li>A log-based <strong>violation ceiling</strong> stops compliance from masking real problems. You cannot reach <em>Exemplary</em> with critical issues in play.</li>
        <li>A <strong>severity grade floor</strong> keeps the label honest. Only an actual critical violation can produce a <em>Critical</em> grade.</li>
      </ul>

      <p>Quodeq ships with ISO 25010 dimensions plus Clean Architecture and DDD. It evaluates any codebase in any language: Python, TypeScript, Go, Rust, Java, Swift, anything. You can also write your own standards for whatever quality means in your project.</p>
    </section>
  );
}

export function GettingStarted() {
  return (
    <section className="help-section">
      <h2>Getting Started</h2>
      <p>The first time you launch Quodeq, the onboarding wizard opens automatically. Four short steps and you have your first evaluation running.</p>

      <h3>The onboarding wizard</h3>
      <ol>
        <li><strong>Welcome</strong> a quick orientation.</li>
        <li><strong>Repo Scan</strong> paste a local path, GitHub URL, or SSH path. Quodeq scans and shows file counts and detected languages.</li>
        <li><strong>Provider</strong> pick where the AI runs. Skipped automatically if you already have one configured.</li>
        <li><strong>Standard Launch</strong> choose dimensions, scope, branch, and a time budget, then start the evaluation.</li>
      </ol>
      <Tip title="Drafts are saved">
        The wizard remembers what you typed. If you close it midway, your draft comes back next time. You can also resume an interrupted setup from the <strong>Projects</strong> tab.
      </Tip>

      <h3>What happens next</h3>
      <ul>
        <li>The <strong>Evaluate</strong> tab streams the run live, including findings as they appear.</li>
        <li>When it finishes, the <strong>Overview</strong> tab opens with grades and top findings.</li>
        <li><strong>Violations</strong>, <strong>Map</strong>, and <strong>History</strong> let you drill in from different angles.</li>
      </ul>

      <h3>Requirements</h3>
      <ul>
        <li><strong>Python 3.12+</strong> and <strong>Node.js 18+</strong>.</li>
        <li>At least one AI provider configured. See <em>AI Providers</em>.</li>
      </ul>
    </section>
  );
}

export function Projects() {
  return (
    <section className="help-section">
      <h2>Projects</h2>
      <p>The <strong>Projects</strong> tab is your home base. Every codebase you evaluate becomes a project with its own grade, score, and run history.</p>

      <h3>What each row tells you</h3>
      <ul>
        <li><strong>Grade and score</strong> from the latest run, on a 0 to 10 scale.</li>
        <li><strong>File and line counts</strong> of the analyzed scope.</li>
        <li><strong>Last run timestamp</strong> and the model that produced it.</li>
        <li><strong>Setup state</strong>: projects with an interrupted onboarding show a <em>Resume setup</em> action.</li>
      </ul>

      <h3>What you can do</h3>
      <KeyTable rows={[
        ['Select project', 'Open it. Goes to Overview if it has runs, otherwise Evaluate.'],
        ['+ Add project', 'Open the wizard at Repo Scan to add another codebase.'],
        ['Resume setup', 'Pick up an interrupted wizard with the same draft.'],
        ['Relocate', 'Update the local path if the repo moved on disk.'],
        ['Export', 'Download the run findings as JSON.'],
        ['Delete', 'Remove the project and all its runs. Not reversible.'],
      ]} />

      <h3>Sub-projects and monorepos</h3>
      <p>You can evaluate a subdirectory of a repository as its own project by setting <strong>Scope</strong> in the wizard or in <em>Evaluate</em>. Each scoped run becomes a distinct project; Quodeq detects the parent-child relationship and groups them in the list so you can compare quality across packages.</p>

      <Tip title="Wiping the slate">
        Projects, runs, and findings live under <code>~/.quodeq</code>. Delete that directory and Quodeq starts fresh, including the welcome wizard.
      </Tip>
    </section>
  );
}

export function Providers() {
  return (
    <section className="help-section">
      <h2>AI Providers</h2>
      <p>Quodeq runs evaluations through one of three provider types. Pick what matches your privacy and cost constraints. You can switch any time from <strong>Settings</strong>.</p>

      <h3>Cloud (OpenRouter or custom)</h3>
      <p>Routes through a hosted API using your key. Good when you want the latest frontier models without installing a CLI.</p>
      <ul>
        <li><strong>OpenRouter</strong> single key, broad catalog. From cheapest to most capable, try <code>meta-llama/llama-3.1-8b-instruct:free</code>, <code>anthropic/claude-haiku-4-5</code>, <code>anthropic/claude-sonnet-4</code>, or <code>anthropic/claude-opus-4-7</code>.</li>
        <li><strong>Custom</strong> any OpenAI-compatible endpoint. You provide the base URL and model id.</li>
      </ul>
      <p>Use <strong>Test connection</strong> in the provider tab to verify the key and model before launching a real run.</p>

      <h3>CLI (Claude Code, Codex)</h3>
      <p>Delegates to an AI CLI you already have authenticated on your machine. The CLI handles auth and billing; Quodeq drives it.</p>
      <ol>
        <li>Install and sign in to your CLI of choice (Claude Code, Codex, etc.).</li>
        <li>In <strong>Settings → CLI Provider</strong>, pick the binary and a model id like <code>gpt-5</code> or <code>claude-sonnet-4-6</code>.</li>
        <li>Optionally pin a different model per power tier (Fast, Balanced, Thorough).</li>
      </ol>

      <h3>Ollama (local, private)</h3>
      <p>Runs entirely on your machine. Code never leaves the host. The trade-off is slower analysis and lower ceiling on quality compared to frontier cloud models.</p>
      <ol>
        <li>Install Ollama from <code>ollama.com</code>.</li>
        <li>Pull a capable instruction model, for example <code>ollama pull gemma4:26b</code>.</li>
        <li>In <strong>Settings → Ollama</strong>, your installed models appear automatically. Pick one and set sub-agent count.</li>
      </ol>
      <Tip title="Picking sub-agent count">
        More sub-agents finish faster but use more tokens (cloud) or more VRAM (local). For local Ollama on a 32 GB machine, start with 2 or 3 and scale up only if you have headroom.
      </Tip>

      <h3>omlx (Apple Silicon only)</h3>
      <p>On Apple Silicon Macs an extra local option appears: <strong>Omlx</strong>, an MLX-native server that runs models tuned for unified memory.</p>
      <ol>
        <li>Start the server with <code>omlx serve</code> or the omlx menu bar app.</li>
        <li>In <strong>Settings → Omlx</strong>, pick a model. The list comes from your local server; add models through the omlx admin UI at <code>http://localhost:8000/admin</code>.</li>
        <li>Under <em>Advanced</em> you can set a custom server address, an API key, and run the parallel-agent auto-detect, which recommends a sub-agent count based on your unified memory.</li>
      </ol>

      <h3>Power tiers</h3>
      <p>Each provider exposes three power levels that map to model size:</p>
      <KeyTable rows={[
        ['Fast', 'Smallest tier. Good for routine runs and tight budgets.'],
        ['Balanced', 'Default. Best quality-per-cost for most evaluations.'],
        ['Thorough', 'Largest tier. Use for first scans, audits, or sensitive areas.'],
      ]} />
    </section>
  );
}

export function Evaluations() {
  return (
    <section className="help-section">
      <h2>Running Evaluations</h2>
      <p>The <strong>Evaluate</strong> tab is where you start, watch, and finish a run. The same screen handles configuration, live progress, and the result hand-off.</p>

      <h3>Inputs</h3>
      <KeyTable rows={[
        ['Local path', <><code>/path/to/your/project</code></>],
        ['GitHub URL', <><code>https://github.com/org/repo</code></>],
        ['SSH path', <><code>git@github.com:org/repo.git</code></>],
      ]} />

      <h3>Options</h3>
      <ul>
        <li><strong>Dimensions</strong> which quality dimensions to include. Hidden dimensions in <em>Standards</em> are skipped automatically.</li>
        <li><strong>Branch</strong> which git branch to analyze. Defaults to the repo default.</li>
        <li><strong>Scope</strong> a subdirectory to focus on, e.g. <code>packages/frontend</code>. Useful for monorepos.</li>
        <li><strong>Sub-agents</strong> how many parallel agents run. Higher is faster, costs more.</li>
        <li><strong>Time budget</strong> a soft cap on run length. Quodeq scores whatever has completed when the timer expires.</li>
      </ul>

      <h3>Incremental and clean scans</h3>
      <p>By default, Quodeq carries findings for unchanged files forward and re-evaluates only files that have changed since the last run. This keeps subsequent scans fast without losing coverage.</p>
      <p>The <strong>Clean scan</strong> toggle forces a full re-analysis of every file. Use it after a big refactor, when you change standards, or whenever you want a fresh start. The toggle has three states:</p>
      <ul>
        <li><strong>Off (default)</strong> incremental behavior. Unchanged-file findings are reused; only changed files are re-evaluated.</li>
        <li><strong>Once</strong> the next scan runs clean. The toggle resets to Off automatically after that run completes.</li>
        <li><strong>Permanent</strong> every scan runs clean until you turn the toggle off. Stored in <code>localStorage</code> so it persists across sessions.</li>
      </ul>
      <p>The Clean scan toggle is available both on the Scan form (before you start) and on the Re-evaluate card (after a run finishes).</p>

      <h3>What you see while it runs</h3>
      <p>The Evaluate tab streams a live phase indicator (detect → analyze → collect → score → report), an active provider badge, a countdown against your time budget, and a feed of findings as the agents discover them. Click any finding in the feed to jump straight to its file context, even mid-run.</p>

      <h3>Cancelling a run</h3>
      <p>Hit <strong>Cancel evaluation</strong> any time. You will be asked whether to <strong>keep partial findings</strong> (everything collected so far is scored as a partial run) or <strong>discard</strong> (the run is dropped). Completed dimensions are always scored on cancel; dimensions in flight stop where they are.</p>

      <h3>When it finishes</h3>
      <p>The result card offers <strong>View results</strong>, <strong>Evaluate again</strong>, or <strong>Back to project</strong>. Each completed run is added to history with its grade, score, and delta from the previous run.</p>

      <Tip title="Re-evaluating an existing project">
        From any project you can launch a fresh run on the same scope. Subsequent runs are added to <em>History</em> so you can track quality over time without losing previous results.
      </Tip>
    </section>
  );
}

export function Dimensions() {
  return (
    <section className="help-section">
      <h2>Quality Dimensions</h2>
      <p>Quodeq evaluates code across six dimensions derived from the ISO/IEC 25010 software-quality standard, plus two architecture dimensions you can opt into.</p>

      <h3>The six ISO dimensions</h3>
      <ul>
        <li><strong>Security</strong> vulnerabilities, authentication, data protection. Examples: SQL injection, hardcoded secrets, missing auth.</li>
        <li><strong>Reliability</strong> error handling, fault tolerance, recovery. Examples: unhandled exceptions, missing retries, resource leaks.</li>
        <li><strong>Maintainability</strong> clarity, modularity, testability. Examples: long functions, duplicated code, tight coupling.</li>
        <li><strong>Performance</strong> efficiency, resource use, scalability. Examples: N+1 queries, memory leaks, missing caching.</li>
        <li><strong>Flexibility</strong> extensibility, configurability, portability. Examples: hardcoded values, missing interfaces, vendor lock-in.</li>
        <li><strong>Usability</strong> API design, documentation, developer experience. Examples: confusing APIs, missing docs, inconsistent naming.</li>
      </ul>

      <h3>Architecture dimensions (opt-in)</h3>
      <ul>
        <li><strong>Clean Architecture</strong> layer separation, dependency rules, import direction, boundary enforcement.</li>
        <li><strong>DDD Design</strong> domain modeling, bounded contexts, aggregates, value objects, ubiquitous language.</li>
      </ul>
      <p>These ship <strong>disabled by default</strong>. Open <em>Standards</em> and click the {ICON_EYE_ON} eye on the dimension card to enable them. Once visible, they appear in Evaluate and Overview alongside the ISO six.</p>

      <h3>Showing and hiding dimensions</h3>
      <p>The {ICON_EYE_ON} <strong>visibility toggle</strong> on each standard card controls whether a dimension is part of evaluations and the Overview. Hide a dimension to ignore it without deleting any standards. Re-enable it any time, the next run will include it.</p>

      <h3>Scoring summary</h3>
      <p>Each dimension is scored 0 to 10 with a letter grade. The project grade averages enabled dimensions. Dimension weights apply only when enabled in Settings, Grade formula. See <em>Philosophy</em> for the full Q² formula.</p>
    </section>
  );
}

export function Violations() {
  return (
    <section className="help-section">
      <h2>Violations &amp; Fix Plans</h2>
      <p>The <strong>Violations</strong> tab is where you triage findings, drill into evidence, and ship fixes. Active and dismissed findings live in their own sub-tabs.</p>

      <h3>Severity levels</h3>
      <ul>
        <li><span className="severity-tag critical">CRITICAL</span> immediate security or reliability risk. Fix now.</li>
        <li><span className="severity-tag major">MAJOR</span> significant quality issue. Fix before the next release.</li>
        <li><span className="severity-tag minor">MINOR</span> improvement opportunity. Fix when convenient.</li>
        <li><span className="severity-tag compliance">COMPLIANT</span> not a violation: code that follows the standard correctly. Lifts the score.</li>
      </ul>

      <p>Each finding includes a file and line, a short reason, the offending code, and a CWE classification. Compliant findings cite the CWE the code is correctly defending against.</p>

      <pre className="help-pre">{`CRITICAL    src/db.py:15        SQL injection via string concatenation     CWE-89
            query = f"SELECT * FROM users WHERE id = {user_id}"

MAJOR       src/auth.py:42      Hardcoded credentials in source code       CWE-798
            credentials = {"user": "admin", "pass": "secret123"}

MINOR       src/utils.py:23     Bare except clause hides errors            CWE-396
            except: pass

COMPLIANT   src/api.py:88       Parameterized query prevents injection     CWE-89
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))`}</pre>

      <h3>Three sub-tabs, one dataset</h3>
      <p>Use the pills at the top of the tab:</p>
      <ul>
        <li><strong>by-dimension</strong> a table of dimensions with their principles indented below, showing critical, major, and minor counts, total violations, and health per row.</li>
        <li><strong>by-file</strong> the same findings arranged as your directory tree, with a breadcrumb you can drill into. Useful for tracking down a single hot spot.</li>
        <li><strong>dismissed</strong> everything you dismissed, with its reason, ready to restore or delete for good.</li>
      </ul>

      <h3>Drilling in</h3>
      <KeyTable rows={[
        ['Click a dimension', 'Open the Explorer with all principles, scores, and findings.'],
        ['Click a principle', 'Open the principle detail with violations grouped by severity and a compliance list.'],
        ['Click a file', 'Open the file detail with every finding (active and compliance) for that file.'],
        ['Click a finding', 'Open the leaf finding card with breadcrumb context.'],
      ]} />

      <h3>Fix plans</h3>
      <p>From any violation, the <strong>Fix plan</strong> button opens a side-pane with a structured remediation packet: file path, line number, code context, the violated principle, and concrete guidance. Copy it and paste into your AI agent or IDE. It is designed to give the receiving model everything it needs to apply the fix without follow-up questions.</p>

      <h3>Dismissing a finding</h3>
      <p>If a finding is a false positive or an accepted trade-off, dismiss it from the violation detail. You will be asked for a reason. Dismissed findings:</p>
      <ul>
        <li>move to the <strong>dismissed</strong> sub-tab,</li>
        <li>are <strong>excluded from scoring</strong> (the dimension score updates immediately),</li>
        <li>are <strong>excluded from future evaluations</strong> for the same principle and file,</li>
        <li>can be <strong>restored</strong> individually or in bulk via <em>Restore all</em>.</li>
      </ul>
      <Tip title="Dismissals are durable">
        Dismissals persist across runs. They are tied to the finding's principle and file, so renaming or moving the file may bring the finding back. That is intentional.
      </Tip>
    </section>
  );
}

export function CodeMap() {
  return (
    <section className="help-section">
      <h2>Code Map</h2>
      <p>The <strong>Map</strong> tab visualizes your codebase as shapes you can scan at a glance. Two metrics, three layouts, six combinations.</p>

      <h3>Pick a metric</h3>
      <ul>
        <li><strong>Health</strong> color encodes the dimension grade of each file. Greener is healthier.</li>
        <li><strong>Violations</strong> color encodes raw violation density, weighted by severity.</li>
      </ul>

      <h3>Pick a layout</h3>
      <KeyTable rows={[
        ['Circle Pack', 'Nested circles sized by line count. Best for spotting heavy files at a glance.'],
        ['Galaxy', 'Force-directed cluster view. Two sub-modes: filesystem (by directory) or standards (by violated principle).'],
        ['Risk Matrix', 'Files plotted by complexity (size) vs. issue density. Top-right quadrant is your priority list.'],
      ]} />

      <h3>Reading the views</h3>
      <ul>
        <li><strong>Large red blocks</strong> big files with many issues, high-impact refactor targets.</li>
        <li><strong>Clusters of red</strong> entire modules drifting from the standard.</li>
        <li><strong>Galaxy by standards</strong> reveals which principles are violated most across the project, regardless of where the files live.</li>
        <li><strong>Green islands</strong>: well-maintained areas. Protect them when refactoring nearby.</li>
      </ul>

      <h3>Drilling in</h3>
      <p>Click any node to drill down. The Map keeps a local breadcrumb so you can pop back without leaving the tab. Click a leaf node to open the file detail, or jump from a galaxy-by-standards cluster directly to the offending principle.</p>
    </section>
  );
}

export function History() {
  return (
    <section className="help-section">
      <h2>History &amp; Trends</h2>
      <p>The <strong>History</strong> tab is your project's quality timeline. Every completed run lives there with its grade, score, and delta from the run before.</p>

      <h3>The run list</h3>
      <ul>
        <li><strong>Grade and score</strong> for each run.</li>
        <li><strong>Delta</strong> against the previous run, so you can spot regressions immediately.</li>
        <li><strong>Run metadata</strong> model, sub-agent count, scope, branch, duration.</li>
        <li><strong>Tombstones</strong> deleted runs leave a marker so the trend stays continuous.</li>
      </ul>

      <h3>The trend chart</h3>
      <p>A small chart above the list plots overall score over time, with per-dimension lines you can toggle. Hover a point to see that run's stats; click to open it.</p>

      <h3>Group the Overview chart by day, week, or month</h3>
      <p>The <em>score history</em> chart on the <strong>Overview</strong> groups runs per day by default. Use the selector in the chart header to switch to <strong>Week</strong> or <strong>Month</strong>. Each bar aggregates the runs of one period, tooltips carry the period label, and your choice is remembered across sessions.</p>
      <p>If all your runs fit inside a single week or month, the chart suggests a finer grouping instead of drawing one lonely bar.</p>
      <HelpFigure caption="The score history header. The select groups bars by day, week, or month.">
        <ScoreGroupingFigure />
      </HelpFigure>

      <h3>Run detail and the navigator</h3>
      <p>Clicking a run opens its <strong>Run Detail</strong> page: the same shell as Overview but locked to that single run. From there, the run navigator at the top lets you step <strong>previous / next / latest</strong> without going back to the list. Drill into any dimension and the Explorer keeps the run id, so you stay anchored to that snapshot.</p>

      <h3>Partial and cancelled runs</h3>
      <p>Cancelled runs that kept their partial findings appear with a <em>partial</em> tag. They count for trend purposes but the Run Detail page makes the partial state obvious so you do not over-interpret it.</p>

      <Tip title="Comparing across time">
        The Run Detail navigator is the fastest way to A/B compare. Open the dimension you care about in run N, hit <em>previous</em>, and watch the principle scores shift.
      </Tip>
    </section>
  );
}

export function GradeFormula() {
  return (
    <section className="help-section">
      <h2>Grade Formula</h2>
      <p>The grade formula turns findings into scores and letter grades. You can tune every part of it: open <strong>Settings</strong>, find the <em>Grade formula</em> section, and press <strong>open editor</strong>. Changes preview live before anything is saved.</p>

      <HelpFigure
        caption="The Grade Formula editor. Parameter tabs on top, live preview strip below."
        srcDark={gradeFormulaDark}
        srcLight={gradeFormulaLight}
        alt="Grade Formula editor showing the preview strip with per-dimension gauges, the severity weight sliders, and the APPLY and RESET buttons"
      />

      <h3>The four tabs</h3>
      <KeyTable rows={[
        ['SEVERITY', 'Weight sliders for critical, major, and minor violation types. A readout shows how much a critical finding currently weighs relative to a minor one.'],
        ['CURVE', 'Shape controls for the scoring curve: strictness K (how fast violations hurt), lift compress (how much compliance evidence can lift), and ceiling scale (the maximum score under violation load).'],
        ['BOUNDARIES', 'Drag the dividers (or focus one and use the arrow keys) between CRITICAL, POOR, ADEQUATE, GOOD, and EXEMPLARY to move the grade thresholds. Severity floors below set the worst score possible when no critical findings exist.'],
        ['DIMENSIONS', 'Optional per-dimension weights. When the toggle is off, the overall grade is a plain mean across dimensions.'],
      ]} />

      <HelpFigure caption="Default severity weights set how hard each finding pushes a score down the curve. Solid line is the base score, dashed is the ceiling.">
        <GradeFormulaCurveFigure />
      </HelpFigure>

      <h3>Preview, then apply</h3>
      <p>The preview strip recomputes your selected project's latest run with the draft parameters and shows before and after, per dimension. Nothing is stored until you press <strong>APPLY</strong>, which saves the formula and rescores every run in every project. <strong>RESET Q²</strong> returns to the built-in defaults, also rescoring everything.</p>

      <Tip title="Where you see the effect">
        Rescoring updates run detail pages, the accumulated overview, trend charts, and project cards. The grade labels from the BOUNDARIES tab drive every gauge and badge in the app.
      </Tip>

      <p>The formula never touches the insufficient-evidence gate. Principles with too little evidence stay Insufficient regardless of your settings.</p>
    </section>
  );
}

export function Standards() {
  return (
    <section className="help-section">
      <h2>Custom Standards</h2>
      <p>The <strong>Standards</strong> tab is where you decide what quality means for your project. Browse, edit, import, and create the rules Quodeq evaluates against.</p>

      <h3>Built-in standards</h3>
      <p>Quodeq ships with managed standards for the six ISO 25010 dimensions plus Clean Architecture and DDD Design. They are <strong>read-only</strong> (you can view them but not edit) and marked as <em>Managed</em>. To turn one off, hide it with the {ICON_EYE_ON} visibility toggle.</p>

      <h3>Creating your own</h3>
      <ol>
        <li>Click <strong>New standard</strong>.</li>
        <li>Name it and pick the dimension it belongs to.</li>
        <li>Add <strong>principles</strong> (categories) and inside each, <strong>requirements</strong> (the specific checks).</li>
        <li>Set a severity per requirement: <code>critical</code>, <code>major</code>, or <code>minor</code>.</li>
        <li>Save. The next evaluation picks it up automatically.</li>
      </ol>
      <p>Custom standards are fully editable and can be duplicated, exported, or deleted at any time.</p>

      <h3>Importing</h3>
      <p>Click <strong>Import</strong> to load a JSON file you wrote yourself or got from elsewhere. Quodeq validates the shape and tells you what is wrong if it does not parse.</p>

      <h3>Standard schema</h3>
      <pre className="help-pre">{`{
  "id": "react-best-practices",
  "name": "React Best Practices",
  "dimension": "maintainability",
  "version": "1.0",
  "principles": [
    {
      "id": "P-REACT-A11Y",
      "name": "Accessibility",
      "description": "Components must be accessible by default.",
      "requirements": [
        {
          "id": "R-A11Y-1",
          "rule": "Interactive elements expose semantic roles.",
          "severity": "major"
        }
      ]
    }
  ]
}`}</pre>
      <ul>
        <li><strong>id</strong> unique slug, used as the filename.</li>
        <li><strong>dimension</strong> which quality dimension this standard rolls up into.</li>
        <li><strong>principles</strong> categories of evaluation. Each principle becomes a card on the Explorer page.</li>
        <li><strong>requirements</strong> specific checks. Each one is what the AI cites when it reports a finding.</li>
      </ul>

      <h3>Generating standards with AI</h3>
      <p>Any chat AI (Claude, ChatGPT, Gemini) can write a standard for you. Paste the schema above, describe what you want evaluated, and ask for a JSON file. Save the result and import it. A starter prompt:</p>
      <pre className="help-pre">{`Generate a Quodeq standard JSON file for evaluating React
component best practices. Cover accessibility, performance,
state management, and error boundaries. Use this schema:
{ ...paste schema above... }`}</pre>
    </section>
  );
}

export function Settings() {
  return (
    <section className="help-section">
      <h2>Settings</h2>
      <p>Provider configuration, model overrides, server status, and appearance live in <strong>Settings</strong>. Most of it is set once and forgotten.</p>

      <h3>Provider tabs</h3>
      <ul>
        <li><strong>Cloud</strong> hosted APIs (OpenRouter or a custom OpenAI-compatible endpoint). API key, base URL, model id, and a <em>Test connection</em> button.</li>
        <li><strong>CLI</strong> local AI CLIs you have authenticated (Claude Code, Codex). Pick the binary, then a model id.</li>
        <li><strong>Ollama</strong> models on your local Ollama server. Quodeq lists whatever you have pulled.</li>
        <li><strong>Omlx</strong> an MLX-native local server. The tab appears only on Apple Silicon Macs.</li>
        <li><strong>llama.cpp</strong> a local llama-server instance. Shows the GGUF currently loaded.</li>
      </ul>
      <p>Each tab also exposes <strong>sub-agent count</strong> and a <strong>time budget</strong> default. Start an evaluation and you can override these per-run.</p>

      <h3>Model overrides per tier</h3>
      <p>Power tiers (Fast / Balanced / Thorough) ship with sensible defaults. You can pin a different model to each tier if you want a small model for routine runs and a large one for audits. Leave a tier blank to inherit the main model.</p>

      <h3>Server</h3>
      <p>Shows the current dashboard server: port, version, and status. Live log streams (server, Ollama, evaluation) are wired into the side-pane log viewer. Open it from the bottom-bar log buttons to tail what is happening.</p>

      <h3>Appearance</h3>
      <p>Light or dark mode plus a theme family selector. Themes change accent colors and surface tones; layout stays the same.</p>

      <h3>Updates</h3>
      <p>Quodeq checks PyPI and GitHub once a day for a newer version. When one exists, a banner appears at the top of the dashboard and the <em>Updates</em> section shows the version jump plus the exact upgrade command for your install (pipx, uv, or Homebrew). Dismissing the banner silences that version; the next release brings it back.</p>
      <ul>
        <li><strong>check now</strong> asks immediately, ignoring the daily throttle.</li>
        <li><strong>Automatic checks</strong> turns the daily background check on or off.</li>
        <li>Set <code>QUODEQ_NO_UPDATE_NOTIFIER=1</code> to disable automatic checks and CLI notices entirely.</li>
      </ul>

      <h3>Grade formula</h3>
      <p>The <em>Grade formula</em> section opens the formula editor, where severity weights, curve shape, grade boundaries, and dimension weights live. See the <strong>Grade Formula</strong> help section for the full tour.</p>

      <h3>About</h3>
      <p>Version info, links to docs and the repo, and the kill-switch environment variables you can set if you need to disable side features. Most users will not need this section.</p>
    </section>
  );
}
