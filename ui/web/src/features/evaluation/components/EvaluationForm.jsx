import { useState } from 'react';
import FolderBrowser from './FolderBrowser.jsx';

const DISCIPLINE_OPTIONS = [
  'backend_springboot_java',
  'backend_springboot_kotlin',
  'backend_typescript_lambdas',
  'cli_bash',
  'frontend_nextjs',
  'frontend_react',
  'infrastructure',
  'mobile_android',
  'mobile_ios',
  'nodejs',
];

const DIMENSION_OPTIONS = [
  { name: 'Affordability',   short: 'aff',  code: 'affordability' },
  { name: 'Availability',    short: 'avl',  code: 'availability' },
  { name: 'Configurability', short: 'cfg',  code: 'configurability' },
  { name: 'Efficiency',      short: 'eff',  code: 'efficiency' },
  { name: 'Evolvability',    short: 'evo',  code: 'evolvability' },
  { name: 'Extensibility',   short: 'ext',  code: 'extensibility' },
  { name: 'Flexibility',     short: 'flx',  code: 'flexibility' },
  { name: 'Maintainability', short: 'mnt',  code: 'maintainability' },
  { name: 'Performance',     short: 'perf', code: 'performance' },
  { name: 'Recoverability',  short: 'rcv',  code: 'recoverability' },
  { name: 'Resilience',      short: 'res',  code: 'resilience' },
  { name: 'Robustness',      short: 'rob',  code: 'robustness' },
  { name: 'Scalability',     short: 'scl',  code: 'scalability' },
  { name: 'Simplicity',      short: 'sim',  code: 'simplicity' },
  { name: 'Usability',       short: 'usx',  code: 'usability' },
];

export default function EvaluationForm({ onStart, disabled }) {
  const [repo, setRepo] = useState('');
  const [discipline, setDiscipline] = useState('');
  const [selectedDimensions, setSelectedDimensions] = useState([]);
  const [numerical, setNumerical] = useState(true);
  const [folderBrowserOpen, setFolderBrowserOpen] = useState(false);

  function toggleDimension(code) {
    setSelectedDimensions((prev) =>
      prev.includes(code) ? prev.filter((d) => d !== code) : [...prev, code]
    );
  }

  function handleSubmit(e) {
    e.preventDefault();
    onStart({
      repo,
      discipline: discipline || undefined,
      dimensions: selectedDimensions.join(','),
      numerical,
    });
    setRepo('');
  }

  function handleFolderSelect(path) {
    setRepo(path);
    setFolderBrowserOpen(false);
  }

  return (
    <>
      <form className="evaluate-form-large" onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="eval-form-repo">Repository</label>
          <div className="repo-input-wrapper">
            <input
              id="eval-form-repo"
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
              placeholder="git@github.com:org/repo.git"
              required
            />
            {repo && (
              <button
                type="button"
                className="input-clear-btn"
                onClick={() => setRepo('')}
                title="Clear"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            )}
            <button
              type="button"
              className="browse-btn"
              onClick={() => setFolderBrowserOpen(true)}
              title="Browse local filesystem"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
              </svg>
              Local
            </button>
          </div>
        </div>

        <div className="form-group">
          <label htmlFor="eval-form-discipline">Discipline (optional)</label>
          <select
            id="eval-form-discipline"
            value={discipline}
            onChange={(e) => setDiscipline(e.target.value)}
          >
            <option value="">— None —</option>
            {DISCIPLINE_OPTIONS.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label>Dimensions to Evaluate</label>
          <div className="dimension-grid">
            {DIMENSION_OPTIONS.map((dim) => (
              <button
                key={dim.code}
                type="button"
                className={`dimension-chip-btn ${selectedDimensions.includes(dim.code) ? 'selected' : ''}`}
                onClick={() => toggleDimension(dim.code)}
              >
                <span className="dim-code">{dim.short}</span>
                <span className="dim-name">{dim.name}</span>
              </button>
            ))}
          </div>
          <div className="dimension-chip-actions">
            <button type="button" onClick={() => setSelectedDimensions(DIMENSION_OPTIONS.map((d) => d.code))}>
              Select All
            </button>
            <button type="button" onClick={() => setSelectedDimensions([])}>
              Clear
            </button>
          </div>
        </div>

        <label className="checkbox-row" htmlFor="eval-form-numerical">
          <input
            id="eval-form-numerical"
            type="checkbox"
            checked={numerical}
            onChange={(e) => setNumerical(e.target.checked)}
          />
          Enable numerical scoring (0-10 scale)
        </label>

        <button type="submit" className="evaluate-submit-btn" disabled={disabled}>
          {disabled ? 'Running Evaluation...' : 'Start Evaluation'}
        </button>
      </form>

      {folderBrowserOpen && (
        <FolderBrowser
          onSelect={handleFolderSelect}
          onClose={() => setFolderBrowserOpen(false)}
        />
      )}
    </>
  );
}
