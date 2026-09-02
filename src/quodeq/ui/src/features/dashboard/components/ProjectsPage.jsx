import { useState } from 'react';
import { TermHeader } from '../../../components/terminal/index.js';
import LoadingScreen from '../../../components/LoadingScreen.jsx';
import { useProjectsPageData } from '../hooks/useProjectsPageData.js';
import { usePullToLocal } from '../hooks/usePullToLocal.js';
import { t } from '../../../strings/index.js';
import { ProjectCard } from './projectCards/ProjectCard.jsx';
import { ProjectCardGroup, useRelocateDialog } from './projectCards/ProjectCardGroup.jsx';
import { OnlineCardFooter } from './projectCards/OnlineCardFooter.jsx';
import { ProjectsToolbar } from './ProjectsToolbar.jsx';

const EVAL_BLOCKED_TITLE = t('projects.evalBlockedTitle');

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
          className={`term-btn term-btn--primary term-btn--filled projects-empty__cta-btn${isEvaluating ? ' is-disabled' : ''}`}
          onClick={onAddProject}
          aria-disabled={isEvaluating || undefined}
          title={isEvaluating ? EVAL_BLOCKED_TITLE : undefined}
        >
          <span aria-hidden="true">▸</span> {t('projects.addProject')}
        </button>
        {onImportProject && (
          <button
            type="button"
            className={`projects-page__import-btn projects-empty__cta-btn${isEvaluating ? ' is-disabled' : ''}`}
            onClick={onImportProject}
            aria-disabled={isEvaluating || undefined}
            title={isEvaluating ? EVAL_BLOCKED_TITLE : t('projects.importTitle')}
          >
            {t('projects.importProject')}
          </button>
        )}
      </div>
    </div>
  );
}

function ProjectsPageHeader({ projectsLoaded, projects, isEmpty, onImportProject, onAddProject, isEvaluating }) {
  return (
    <div className="projects-page__header">
      <TermHeader
        name={t('projects.termName')}
        sub={
          projectsLoaded
            ? (projects.length === 1
                ? t('projects.reposEvaluatedOne', { count: projects.length })
                : t('projects.reposEvaluatedMany', { count: projects.length }))
            : t('overview.loading')
        }
      />
      {!isEmpty && (
        <div className="projects-page__header-actions">
          {onImportProject && (
            <button
              type="button"
              className={`projects-page__import-btn${isEvaluating ? ' is-disabled' : ''}`}
              onClick={onImportProject}
              aria-label={t('projects.importAria')}
              aria-disabled={isEvaluating || undefined}
              title={isEvaluating ? EVAL_BLOCKED_TITLE : t('projects.importTitle')}
            >
              {t('projects.importProject')}
            </button>
          )}
          {onAddProject && (
            <button
              type="button"
              className={`term-btn term-btn--primary term-btn--filled projects-page__add-btn${isEvaluating ? ' is-disabled' : ''}`}
              onClick={onAddProject}
              aria-label={t('projects.addAria')}
              aria-disabled={isEvaluating || undefined}
              title={isEvaluating ? EVAL_BLOCKED_TITLE : undefined}
            >
              <span aria-hidden="true">▸</span> {t('projects.addProject')}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function LocalProjectEntry({ entry, ctx }) {
  const { children, selectedProject, onSelect, onResumeSetup, confirming, setConfirming, onDelete, onExport, relocateActions, publishActions, localEntryById, shared } = ctx;
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
  const { onSelect, pullConflictId, handlePull, handleConfirmCopy, cancelConflict, pulledIds } = ctx;
  const sharedId = entry.shared.id || entry.shared.name || entry.shared;
  return (
    <ProjectCard
      key={entry.key}
      project={entry.shared}
      chips="shared"
      cardProps={{
        onSelect: (pid) => onSelect?.(pid, 'shared'),
        footer: (
          <OnlineCardFooter
            projectId={sharedId}
            onPull={handlePull}
            pullConflict={pullConflictId === sharedId}
            onConfirmCopy={handleConfirmCopy}
            onCancelConflict={cancelConflict}
            pulled={pulledIds.has(sharedId)}
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
  return (
    <div className="projects-cards">
      {visibleEntries.map((entry) => (
        entry.local
          ? <LocalProjectEntry key={entry.key} entry={entry} ctx={ctx} />
          : <SharedProjectEntry key={entry.key} entry={entry} ctx={ctx} />
      ))}
    </div>
  );
}

function ProjectsPageBody({ filters, onFiltersChange, shared, visibleEntries, cardsListCtx }) {
  return (
    <>
      <ProjectsToolbar
        filters={filters}
        onFiltersChange={onFiltersChange}
        configured={shared.configured}
        lastSynced={shared.lastSynced}
        stale={shared.stale}
        error={shared.error}
        refreshing={shared.refreshing}
        onRefresh={shared.refresh}
      />
      <ProjectsCardsList visibleEntries={visibleEntries} ctx={cardsListCtx} />
    </>
  );
}

export default function ProjectsPage({ projects = [], projectsLoaded = true, selectedProject, isEvaluating = false, filters, actions }) {
  const {
    onSelect, onDelete, onExport, onRelocate, onAddProject, onImportProject,
    onResumeSetup, onFiltersChange, onProjectsReload,
  } = actions;
  const [confirming, setConfirming] = useState(null);
  const relocateActions = useRelocateDialog(onRelocate);

  // The merge/filter memo chain (shared sync, publish state, local/shared
  // merge, subproject nesting, query filter) is extracted verbatim into
  // useProjectsPageData -- same hooks, same deps, same order.
  const { shared, children, localEntryById, publishActions, isEmpty, visibleEntries } = useProjectsPageData({ projects, filters });

  const { pullConflictId, pulledIds, handlePull, handleConfirmCopy, cancelConflict } = usePullToLocal({ shared, onProjectsReload });

  const cardsListCtx = {
    children, selectedProject, onSelect, onResumeSetup, confirming, setConfirming, onDelete, onExport,
    relocateActions, publishActions, localEntryById, shared, pullConflictId, handlePull, handleConfirmCopy,
    cancelConflict, pulledIds,
  };

  return (
    <section className="projects-page projects-page--terminal">
      <ProjectsPageHeader
        projectsLoaded={projectsLoaded}
        projects={projects}
        isEmpty={isEmpty}
        onImportProject={onImportProject}
        onAddProject={onAddProject}
        isEvaluating={isEvaluating}
      />
      {!projectsLoaded ? (
        <LoadingScreen variant="inline" />
      ) : isEmpty ? (
        <EmptyProjectsCTA onAddProject={onAddProject} onImportProject={onImportProject} isEvaluating={isEvaluating} />
      ) : (
        <ProjectsPageBody
          filters={filters}
          onFiltersChange={onFiltersChange}
          shared={shared}
          visibleEntries={visibleEntries}
          cardsListCtx={cardsListCtx}
        />
      )}
    </section>
  );
}
