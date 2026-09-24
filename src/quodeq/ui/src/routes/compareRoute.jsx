/**
 * The Compare tab's route renderer, moved out of routes/renderers.jsx
 * verbatim (move-only refactor).
 */
import { lazy } from 'react';
import { PROJECT_SOURCE } from '../vocab/projectSource.js';
import { NAV_TAB } from '../vocab/navTab.js';

const ComparePage = lazy(() => import('../features/compare/components/ComparePage.jsx'));

export function compareRoute(params, props) {
  return (
    <ComparePage
      projects={props.navigation.projects}
      projectsLoaded={props.navigation.projectsLoaded}
      dimension={params.dimension || null}
      onOpenProject={(id, source = PROJECT_SOURCE.LOCAL) => {
        // Remote fleet rows open through the shared source; the same
        // machinery the projects drawer uses for shared selections.
        props.navigation.handleProjectChange(id, source);
        props.navigation.navTab(NAV_TAB.OVERVIEW);
      }}
      // Drill-down is a real nav-stack entry: push from the fleet so the
      // browser back button returns there; replace when switching between
      // dimensions so tab-hopping doesn't grow history.
      onOpenDimension={(key) => props.navigation.handleNavigate(NAV_TAB.COMPARE, { dimension: key })}
      onSwitchDimension={(key) => props.navigation.handleNavigateReplace(NAV_TAB.COMPARE, { dimension: key })}
      // Cross-project principle jump: the evalPrincipal carries its own
      // project, so the selection doesn't change and back pops to Compare.
      onOpenEvalPrincipal={(evalPrincipal) => props.navigation.handleNavigate(NAV_TAB.EVAL_PRINCIPLE, { evalPrincipal, sourceTab: NAV_TAB.COMPARE })}
      // Standings row -> that project's own screen of the SAME dimension
      // (the explorer's cross-project fromProject entry), pushed for the
      // same back-pops-to-Compare contract.
      onOpenProjectDimension={(target) => props.navigation.handleNavigate(NAV_TAB.EXPLORER, {
        dimension: target.dimName,
        runId: target.runId,
        dateLabel: target.dateLabel,
        fromProject: target.id,
        // The entry's own source, like its own project: the explorer must
        // read a local fromProject from the local API even while the
        // global selection sits on the shared source (and vice versa).
        fromSource: target.source || PROJECT_SOURCE.LOCAL,
        sourceTab: NAV_TAB.COMPARE,
      })}
      // Head-to-head is a push like the dimension drill-down: back returns
      // to the fleet with the two-project scope still selected.
      duel={params.duel || null}
      onOpenDuel={(ids) => props.navigation.handleNavigate(NAV_TAB.COMPARE, { duel: ids })}
      onBack={props.navigation.navPop}
    />
  );
}
