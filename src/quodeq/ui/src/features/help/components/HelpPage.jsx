import { useState } from 'react';
import HelpMarkdown from './HelpMarkdown.jsx';
import { TermHeader } from '../../../components/terminal/index.js';
import BrandCarousel from '../../../components/BrandCarousel.jsx';
import { t } from '../../../strings/index.js';

// Help content is per-locale markdown. Swapping languages later means adding
// content/<locale>/ and picking the directory here; nothing else moves.
const SECTION_SOURCES = import.meta.glob('../content/en/*.md', {
  query: '?raw', import: 'default', eager: true,
});

function sourceFor(id) {
  return SECTION_SOURCES[`../content/en/${id}.md`] ?? '';
}

// id -> markdown file stem in content/<locale>/, and the nav label key.
const SECTIONS = [
  { id: 'philosophy', labelKey: 'help.navPhilosophy' },
  { id: 'getting-started', labelKey: 'help.navGettingStarted' },
  { id: 'projects', labelKey: 'help.navProjects' },
  { id: 'shared-repo', labelKey: 'help.navSharedRepo' },
  { id: 'providers', labelKey: 'help.navProviders' },
  { id: 'evaluations', labelKey: 'help.navEvaluations' },
  { id: 'overview', labelKey: 'help.navOverview' },
  { id: 'compare', labelKey: 'help.navCompare' },
  { id: 'dimensions', labelKey: 'help.navDimensions' },
  { id: 'violations', labelKey: 'help.navViolations' },
  { id: 'map', labelKey: 'help.navMap' },
  { id: 'history', labelKey: 'help.navHistory' },
  { id: 'grade-formula', labelKey: 'help.navGradeFormula' },
  { id: 'standards', labelKey: 'help.navStandards' },
  { id: 'assistant', labelKey: 'help.navAssistant' },
  { id: 'terminal', labelKey: 'help.navTerminal' },
  { id: 'settings', labelKey: 'help.navSettings' },
  { id: 'cli', labelKey: 'help.navCli' },
];

function SectionNav({ active, onSelect }) {
  return (
    <nav className="help-section-nav">
      {SECTIONS.map(s => (
        <button
          key={s.id}
          className={`help-section-btn${active === s.id ? ' active' : ''}`}
          onClick={() => onSelect(s.id)}
          aria-pressed={active === s.id}
        >
          {t(s.labelKey)}
        </button>
      ))}
    </nav>
  );
}

export default function HelpPage() {
  const [activeSection, setActiveSection] = useState('philosophy');

  return (
    <div className="help-page help-page--terminal">
      <div className="help-header">
        <TermHeader
          name={t('help.termName')}
          sub={t('help.termSub')}
        />
        <BrandCarousel />
      </div>
      <div className="help-layout">
        <SectionNav active={activeSection} onSelect={setActiveSection} />
        <div className="help-content">
          <HelpMarkdown source={sourceFor(activeSection)} />
        </div>
      </div>
    </div>
  );
}
