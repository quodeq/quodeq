import { useState } from 'react';
import {
  Philosophy,
  GettingStarted,
  Projects,
  Providers,
  Evaluations,
  Dimensions,
  Violations,
  CodeMap,
  History,
  GradeFormula,
  Standards,
  Settings,
} from './HelpSections.jsx';
import { TermHeader } from '../../../components/terminal/index.js';
import BrandCarousel from '../../../components/BrandCarousel.jsx';

const SECTIONS = [
  { id: 'philosophy', label: 'Philosophy' },
  { id: 'getting-started', label: 'Getting Started' },
  { id: 'projects', label: 'Projects' },
  { id: 'providers', label: 'AI Providers' },
  { id: 'evaluations', label: 'Running Evaluations' },
  { id: 'dimensions', label: 'Quality Dimensions' },
  { id: 'violations', label: 'Violations & Fix Plans' },
  { id: 'map', label: 'Code Map' },
  { id: 'history', label: 'History & Trends' },
  { id: 'grade-formula', label: 'Grade Formula' },
  { id: 'standards', label: 'Custom Standards' },
  { id: 'settings', label: 'Settings' },
];

const SECTION_COMPONENTS = {
  'philosophy': Philosophy,
  'getting-started': GettingStarted,
  'projects': Projects,
  'providers': Providers,
  'evaluations': Evaluations,
  'dimensions': Dimensions,
  'violations': Violations,
  'map': CodeMap,
  'history': History,
  'grade-formula': GradeFormula,
  'standards': Standards,
  'settings': Settings,
};

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
          {s.label}
        </button>
      ))}
    </nav>
  );
}

export default function HelpPage() {
  const [activeSection, setActiveSection] = useState('philosophy');
  const Section = SECTION_COMPONENTS[activeSection] || Philosophy;

  return (
    <div className="help-page help-page--terminal">
      <div className="help-header">
        <TermHeader
          name="help"
          sub="how quodeq works and how to get the most out of it"
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
