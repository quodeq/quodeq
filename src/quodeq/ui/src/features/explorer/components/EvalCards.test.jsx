import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ComplianceCard } from './EvalCards.jsx';
import { t } from '../../../strings/index.js';

const item = { file: 'src/a.py', line: 1, principle: 'P1', title: 'ok', reason: null, snippet: null, context: null };

describe('ComplianceCard', () => {
  it('says the detail could not be loaded when its fetch failed', () => {
    render(<ComplianceCard c={{ ...item, detailUnavailable: true }} principle="P1" index={0} />);
    expect(screen.getByText(t('explorer.detailUnavailable'))).toBeInTheDocument();
  });

  it('says the finding changed when its detail row no longer exists on the server', () => {
    render(<ComplianceCard c={{ ...item, detailOutdated: true }} principle="P1" index={0} />);
    expect(screen.getByText(t('explorer.detailOutdated'))).toBeInTheDocument();
    expect(screen.queryByText(t('explorer.detailUnavailable'))).not.toBeInTheDocument();
  });

  it('shows no note for an item whose detail is present or still loading', () => {
    render(<ComplianceCard c={{ ...item, detailDeferred: true }} principle="P1" index={0} />);
    expect(screen.queryByText(t('explorer.detailUnavailable'))).not.toBeInTheDocument();
  });
});
