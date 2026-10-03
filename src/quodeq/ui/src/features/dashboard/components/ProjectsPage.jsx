import { useCallback, useState } from 'react';
import LoadingScreen from '../../../components/LoadingScreen.jsx';
import { useProjectsPageData } from '../hooks/useProjectsPageData.js';
import { usePullToLocal } from '../hooks/usePullToLocal.js';
import { t } from '../../../strings/index.js';
import { ProjectCard } from './projectCards/ProjectCard.jsx';
import { ProjectCardGroup, useRelocateDialog } from './projectCards/ProjectCardGroup.jsx';
import { OnlineCardFooter } from './projectCards/OnlineCardFooter.jsx';
import { ProjectsToolbar } from './ProjectsToolbar.jsx';
import { ProjectsPageHeader, EVAL_BLOCKED_TITLE } from './ProjectsPageHeader.jsx';
import { TeamResultsArea } from './TeamResultsArea.jsx';
import { evalBlockedClass, evalBlockedProps } from '../../../utils/evalBlocked.js';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';
import { projectIdOrSelf } from '../../../utils/projectIdentity.js';
import { isSlotActive } from '../../../api/syncStatus.js';

function EmptyProjectsCTA({ onAddProject, onImportProject, isEvaluating }) {
  // The button stays clickable while evaluating so the handler can fire a
  // snackbar explaining the block. ``aria-disabled`` + the visual muted class
  // preserve the disabled affordance without swallowing the click.
  return (
    <div className="projects-empty projects-empty--cta">
      <h3 className="projects-empty__title">{t('projects.addFirstTitle')}</h3>
      <p className="projects-empty__hint">
        {t('projects.addFirstHint')}
      </p>
      <div className="projects-empty__cta-row">
        <button
          type="button"
          className={`term-btn term-btn--primary term-btn--filled projects-empty__cta-btn${evalBlockedClass(isEvaluating)}`}
          onClick={onAddProject}
          {...evalBlockedProps(isEvaluating, EVAL_BLOCKED_TITLE)}
        >
          <span aria-hidden="true">▸</span> {t('projects.addProject')}
        </button>
        {onImportProject && (
          <button
            type="button"
            className={`projects-page__import-btn projects-empty__cta-btn${evalBlockedClass(isEvaluating)}`}
            onClick={onImportProject}
            {...evalBlockedProps(isEvaluating, EVAL_BLOCKED_TITLE, t('projects.importTitle'))}
          >
            {t('projects.importProject')}
          </button>
        )}
      </div>
    </div>
  );
}

// The three bundles a local card needs: what the project is, whether it is
// the selected one, and what can be done to it.
function localEntryProps(ctx) {
  return {
    project: { children: ctx.children, localEntryById: ctx.localEntryById, shared: ctx.shared },
    selection: { selectedProject: ctx.selectedProject, onSelect: ctx.onSelect },
    actions: {
      onResumeSetup: ctx.onResumeSetup,
      confirming: ctx.confirming,
      setConfirming: ctx.setConfirming,
      onDelete: ctx.onDelete,
      onExport: ctx.onExport,
      relocateActions: ctx.relocateActions,
      publishActions: ctx.publishActions,
    },
  };
}

function LocalProjectEntry({ entry, project, selection, actions }) {
  const { children, localEntryById, shared } = project;
  const { selectedProject, onSelect } = selection;
  const { onResumeSetup, confirming, setConfirming, onDelete, onExport, relocateActions, publishActions } = actions;
  return (
    <ProjectCardGroup
      key={entry.key}
      p={entry.local}
      children={children}
      selectedProject={selectedProject}
      onSelect={onSelect}
      onResumeSetup={onResumeSetup}
      dialogActions={{
        confirmActions: { confirming, setConfirming, onDelete, onExport },
        relocateActions,
      }}
      publishActions={publishActions}
      action={entry.action}
      chips={shared.configured ? entry.chips : null}
      publishedAt={entry.local?.publishedAt ?? entry.shared?.publishedAt}
      entryLookup={localEntryById}
    />
  );
}

function SharedProjectEntry({ entry, ctx }) {
  const { onSelect, pullConflictId, pullingId, pullError, handlePull, handleConfirmCopy, cancelConflict, pulledIds } = ctx;
  const sharedId = projectIdOrSelf(entry.shared);
  return (
    <ProjectCard
      key={entry.key}
      project={entry.shared}
      chips={PROJECT_SOURCE.SHARED}
      cardProps={{
        onSelect: (pid) => onSelect?.(pid, PROJECT_SOURCE.SHARED),
        footer: (
          <OnlineCardFooter
            projectId={sharedId}
            onPull={handlePull}
            pullConflict={pullConflictId === sharedId}
            onConfirmCopy={handleConfirmCopy}
            onCancelConflict={cancelConflict}
            pulled={pulledIds.has(sharedId)}
            pulling={pullingId === sharedId}
            pullBusy={Boolean(pullingId)}
            pullError={pullError?.projectId === sharedId ? pullError.message : null}
          />
        ),
      }}
    />
  );
}

function ProjectsCardsList({ visibleEntries, ctx }) {
  if (visibleEntries.length === 0) {
    return <div className="projects-empty">{t('projects.noMatches')}</div>;
  }
  const localProps = localEntryProps(ctx);
  return (
    <div className="projects-cards">
      {visibleEntries.map((entry) => (
        entry.local
          ? <LocalProjectEntry key={entry.key} entry={entry} {...localProps} />
          : <SharedProjectEntry key={entry.key} entry={entry} ctx={ctx} />
      ))}
    </div>
  );
}

function ProjectsPageBody({ filters, onFiltersChange, shared, visibleEntries, cardsListCtx }) {
  return (
    <>
      <ProjectsToolbar filters={filters} onFiltersChange={onFiltersChange} configured={shared.configured} />
      <ProjectsCardsList visibleEntries={visibleEntries} ctx={cardsListCtx} />
    </>
  );
}

// Everything the cards list needs: the merged/filtered entries plus the
// per-card action context (confirm/relocate dialogs, publish, pull-to-local).
function useProjectsCardsCtx({ projects, filters, selectedProject, actions }) {
  const { onSelect, onDelete, onExport, onRelocate, onResumeSetup } = actions;
  const [confirming, setConfirming] = useState(null);
  const relocateActions = useRelocateDialog(onRelocate);

  // The merge/filter memo chain (shared sync, publish state, local/shared
  // merge, subproject nesting, query filter) lives in useProjectsPageData.
  const { shared, children, localEntryById, publishActions, isEmpty, visibleEntries } = useProjectsPageData({ projects, filters });

  const { pullConflictId, pullingId, pullError, pulledIds, handlePull, handleConfirmCopy, cancelConflict } = usePullToLocal({ shared });

  const cardsListCtx = {
    children, selectedProject, onSelect, onResumeSetup, confirming, setConfirming, onDelete, onExport,
    relocateActions, publishActions, localEntryById, shared, pullConflictId, pullingId, pullError, handlePull, handleConfirmCopy,
    cancelConflict, pulledIds,
  };
  return { shared, isEmpty, visibleEntries, cardsListCtx };
}

// The page has four mutually exclusive bodies. A function rather than a
// ternary chain in the JSX, so each branch reads on its own line. While a
// connect is still reading the team's projects, an empty page is not "add
// your first project": the strip above says what is happening, so one quiet
// line says where the results will land.
function ProjectsPageContent({ projectsLoaded, isEmpty, connectActive, emptyProps, bodyProps }) {
  if (!projectsLoaded) return <LoadingScreen variant="inline" />;
  if (isEmpty && connectActive) return <p className="projects-empty">{t('projects.teamResultsArriving')}</p>;
  if (isEmpty) return <EmptyProjectsCTA {...emptyProps} />;
  return <ProjectsPageBody {...bodyProps} />;
}

export default function ProjectsPage({ projects = [], projectsLoaded = true, selectedProject, isEvaluating = false, filters, actions }) {
  const { onAddProject, onImportProject, onFiltersChange, onSharedDisconnected } = actions;
  const { shared, isEmpty, visibleEntries, cardsListCtx } = useProjectsCardsCtx({ projects, filters, selectedProject, actions });
  // The connect card, opened by the header's "connect evaluations repository" or the strip's "change repository".
  const [connectOpen, setConnectOpen] = useState(false);
  const toggleConnect = useCallback(() => setConnectOpen((open) => !open), []);

  return (
    <section className="projects-page projects-page--terminal">
      <ProjectsPageHeader
        counts={{ projectsLoaded, localCount: projects.length, teamCount: shared.projects.length }}
        isEmpty={isEmpty}
        configured={shared.configured}
        connectOpen={connectOpen}
        onToggleConnect={toggleConnect}
        onImportProject={onImportProject}
        onAddProject={onAddProject}
        isEvaluating={isEvaluating}
      />
      <TeamResultsArea
        shared={shared}
        connectOpen={connectOpen}
        onConnectOpenChange={setConnectOpen}
        emptyPage={projectsLoaded && isEmpty}
        onSharedDisconnected={onSharedDisconnected}
      />
      <ProjectsPageContent
        projectsLoaded={projectsLoaded}
        isEmpty={isEmpty}
        connectActive={isSlotActive(shared.status?.connect)}
        emptyProps={{ onAddProject, onImportProject, isEvaluating }}
        bodyProps={{ filters, onFiltersChange, shared, visibleEntries, cardsListCtx }}
      />
    </section>
  );
}
