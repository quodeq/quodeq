import { useState } from 'react';
import LoadingScreen from '../../../components/LoadingScreen.jsx';
import { useProjectsPageData } from '../hooks/useProjectsPageData.js';
import { usePullToLocal } from '../hooks/usePullToLocal.js';
import { t } from '../../../strings/index.js';
import { useRelocateDialog } from '../hooks/useRelocateDialog.js';
import { ProjectsToolbar } from './ProjectsToolbar.jsx';
import { ProjectsPageHeader } from './ProjectsPageHeader.jsx';
import { TeamSyncBand, ConnectFailureArea } from './TeamResultsArea.jsx';
import { ProjectsTable, ProjectsTableHead, ProjectsRows } from './projectsTable/ProjectsTable.jsx';
import { nextSort } from '../projectsSort.js';
import { isCloningProject } from '../../../utils/cloningProject.js';
import { isSlotActive } from '../../../api/syncStatus.js';
import { SYNC_PHASE } from '../../../vocab/syncPhase.js';
import { useCloneGhost } from '../hooks/useCloneGhost.js';
import CloningTile from './CloningTile.jsx';

// While a connect reads the team's projects, one placeholder row per
// project found so far heads the list; they become the real rows when
// reading finishes. Hidden from assistive tech: the band's live region
// already says "reading projects · N found", one announcement, not N.
function ReadingPlaceholders({ count }) {
  if (!count) return null;
  return (
    <div className="projects-placeholders" aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="projects-row projects-row--placeholder">
          <span className="projects-row--placeholder__line projects-row--placeholder__line--name" />
          <span className="projects-row--placeholder__line projects-row--placeholder__line--meta" />
        </div>
      ))}
    </div>
  );
}

// A local row whose clone is still running stays behind the clone row:
// without this the clone row and a "Path not found" row would both show for
// the same repository (see utils/cloningProject.js).
function ProjectsPageBody({ filters, onFiltersChange, shared, visibleEntries, rowsCtx, ghost, cloneSlot, readingCount }) {
  const entries = cloneSlot ? visibleEntries.filter((entry) => !isCloningProject(entry.local, cloneSlot)) : visibleEntries;
  const onSort = (key) => onFiltersChange?.({ ...filters, ...nextSort(filters, key) });
  return (
    <>
      <ProjectsTableHead filters={filters} onSort={onSort} configured={shared.configured} />
      {ghost}
      <ReadingPlaceholders count={readingCount} />
      <ProjectsRows entries={entries} ctx={rowsCtx} />
    </>
  );
}

// Everything the rows need: the merged/filtered entries plus the per-row
// action context (confirm/relocate, publish, pull-to-local).
function useProjectsRowsCtx({ projects, filters, selectedProject, actions }) {
  const { onSelect, onDelete, onExport, onRelocate, onResumeSetup } = actions;
  const [confirming, setConfirming] = useState(null);
  const relocateActions = useRelocateDialog(onRelocate);

  // The merge/filter memo chain (shared sync, publish state, local/shared
  // merge, subproject nesting, query filter) lives in useProjectsPageData.
  const { shared, children, localEntryById, publishActions, isEmpty, visibleEntries } = useProjectsPageData({ projects, filters });

  const { pullConflictId, pullingId, pullError, pulledIds, handlePull, handleConfirmCopy, cancelConflict } = usePullToLocal({ shared });

  const rowsCtx = {
    children, selectedProject, onSelect, onResumeSetup, confirming, setConfirming, onDelete, onExport,
    relocateActions, publishActions, localEntryById, configured: shared.configured, pullConflictId, pullingId, pullError,
    handlePull, handleConfirmCopy, cancelConflict, pulledIds,
  };
  return { shared, isEmpty, visibleEntries, rowsCtx };
}

// The page has four mutually exclusive bodies. A function rather than a
// ternary chain in the JSX, so each branch reads on its own line. The empty
// page keeps the header's actions and says there is nothing yet; the ways
// in are the header's buttons (and the welcome, on a first start). While a
// connect is still reading the team's projects, the band above says what
// is happening, so one quiet line says where the results will land. The
// same goes for a clone that is running: its row heads the table and one
// line says what comes next.
function ProjectsPageContent({ projectsLoaded, isEmpty, status, ghost, bodyProps }) {
  if (!projectsLoaded) return <LoadingScreen variant="inline" />;
  if (isEmpty && status.cloneActive) return <>{ghost}<p className="projects-empty">{t('projects.projectArriving')}</p></>;
  if (isEmpty && (status.connectActive || status.warmingActive)) {
    return <>{ghost}<ReadingPlaceholders count={status.readingCount} /><p className="projects-empty">{t('projects.teamResultsArriving')}</p></>;
  }
  if (isEmpty) return <>{ghost}<p className="projects-empty">{t('projects.noReposYet')}</p></>;
  return <ProjectsPageBody {...bodyProps} ghost={ghost} readingCount={status.readingCount} />;
}

function useGhostTile() {
  const { slot, active, onRetry, onClose } = useCloneGhost();
  const ghost = slot ? <CloningTile slot={slot} onRetry={onRetry} onClose={onClose} /> : null;
  return { ghost, cloneActive: active, cloneSlot: active ? slot : null };
}

// How many of the team's projects are still to come: the ones a running
// connect has found so far, then the ones the server is still warming and
// has not listed yet (its rows land one by one, each ready to open).
function readingCount(shared) {
  const connect = shared.status?.connect;
  if (connect?.phase === SYNC_PHASE.READING) return connect.projectsFound ?? 0;
  return shared.warming?.remaining ?? 0;
}

export default function ProjectsPage({ projects = [], projectsLoaded = true, selectedProject, isEvaluating = false, filters, actions }) {
  const { onAddProject, onImportProject, onConnectEvaluations, onFiltersChange, onSharedDisconnected } = actions;
  const { shared, isEmpty, visibleEntries, rowsCtx } = useProjectsRowsCtx({ projects, filters, selectedProject, actions });
  const { ghost, cloneActive, cloneSlot } = useGhostTile();

  return (
    <section className="projects-page projects-page--terminal">
      <ProjectsPageHeader
        counts={{ projectsLoaded, localCount: projects.length, teamCount: shared.projects.length }}
        configured={shared.configured}
        onConnectEvaluations={onConnectEvaluations}
        onImportProject={onImportProject}
        onAddProject={onAddProject}
        isEvaluating={isEvaluating}
      />
      <ConnectFailureArea shared={shared} />
      {projectsLoaded && !isEmpty && (
        <ProjectsToolbar filters={filters} onFiltersChange={onFiltersChange} configured={shared.configured} />
      )}
      <ProjectsTable
        configured={shared.configured}
        band={<TeamSyncBand shared={shared} onConnectEvaluations={onConnectEvaluations} onSharedDisconnected={onSharedDisconnected} />}
      >
        <ProjectsPageContent
          projectsLoaded={projectsLoaded}
          isEmpty={isEmpty}
          status={{
            connectActive: isSlotActive(shared.status?.connect), cloneActive,
            warmingActive: !!shared.warming?.active, readingCount: readingCount(shared),
          }}
          ghost={ghost}
          bodyProps={{ filters, onFiltersChange, shared, visibleEntries, rowsCtx, cloneSlot }}
        />
      </ProjectsTable>
    </section>
  );
}
