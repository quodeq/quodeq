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

  it('shows a loading skeleton, and no note, while the detail is still deferred', () => {
    render(<ComplianceCard c={{ ...item, detailDeferred: true }} principle="P1" index={0} />);
    expect(screen.getByRole('status', { name: t('explorer.detailLoading') })).toBeInTheDocument();
    expect(screen.queryByText(t('explorer.detailUnavailable'))).not.toBeInTheDocument();
  });

  it('shows neither once the detail is present', () => {
    render(<ComplianceCard c={{ ...item, reason: 'why', detailDeferred: false }} principle="P1" index={0} />);
    expect(screen.getByText('why')).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
