/**
 * API client / repository layer.
 *
 * Every public function maps a raw JSON response to a typed model object
 * (see ../models/) so components never see raw API shapes.
 *
 * This module is a barrel: the actual implementations live in domain
 * modules (projects.js, evaluations.js, scores.js, gradeFormula.js,
 * providers.js, localModels.js, updates.js, plus standards/findings/
 * assistant/shared/terminal), re-exported here for backward compatibility
 * so every existing `from '../api'` / `from './api/index.js'` import keeps
 * working unchanged.
 */

export { listDismissedFindings, dismissFinding, dismissByType, restoreFinding, restoreAllFindings, getRescore, deleteFinding, deleteAllFindings, listVerifiedFindings, unverifyFinding } from './findings.js';
export { listStandards, getStandard, createStandard, updateStandard, deleteStandard, duplicateStandard, listLibrary, listCwes, importFromLibrary, importStandard, exportStandard, getStandardsOverrides, putStandardsOverrides } from './standards.js';
export {
  createAssistantSession, fetchAssistantWorkspace, postAssistantMessage, stopAssistantTurn,
  applyAssistantAction, rejectAssistantAction, assistantEventsUrl,
  applyAssistantWorkspace, createAssistantWorkspacePr, discardAssistantWorkspace, fetchAssistantWorkspaceDiff,
} from './assistant.js';
export {
  getSharedStatus, connectShared, disconnectShared,
  sharedListProjects, sharedGetProjectInfo, sharedGetRuns,
  sharedGetDashboard, sharedGetAccumulated, sharedGetProjectScores,
  sharedGetRunScores, sharedGetFindingDetail, sharedGetDimensionEval, sharedGetViolations,
  sharedListDismissedFindings, sharedListVerifiedFindings,
  publishProject, sharedGetCompareSummary, sharedGetFleetCompare,
} from './shared.js';
export { getSyncStatus, startRefresh, startPull, getInvite } from './syncStatus.js';
export { getCloneStatus, isCloneActive, cloneNameFromUrl } from './projectClone.js';
export { listTerminalSessions, createTerminalSession, killTerminalSession, killTerminal } from './terminal.js';

export {
  getHealth, listProjects, getProjectInfo, getProjectScan, deleteProject,
  getProjectExportUrl, relocateProject, browseDirectory, createDirectory,
  listPlugins, scanPath, importProject, registerProject,
} from './projects.js';

export {
  listEvaluations, startEvaluation, getEvaluation, getEvaluationProgress,
  cancelEvaluation, deleteEvaluation,
} from './evaluations.js';

export {
  getProjectScores, getRunScores, getCompareSummary, getFleetCompare, getDashboard,
  getAccumulated, getDimensionEval, getLiveFindings, getComplianceDetail, getFindingDetail,
} from './scores.js';

export {
  getGradeFormula, saveGradeFormula, resetGradeFormula, previewGradeFormula,
} from './gradeFormula.js';

export { getGradeExplain, previewGradeExplain } from './gradeExplain.js';
export { getRunDiff } from './runDiff.js';

export {
  getAiClients, getClientModels, checkCmdPath, testProviderConnection,
  getKnownModels, getProviderConfigs,
} from './providers.js';

export {
  getOllamaStatus, getOllamaModels, testOllamaConcurrency,
  getLlamacppStatus, getLlamacppLogAvailable, getLlamacppModels, testLlamacppConcurrency,
  getOmlxStatus, getOmlxModels, testOmlxConcurrency,
} from './localModels.js';

export {
  getUpdateStatus, checkForUpdates, dismissUpdate, setUpdateAutoCheck, markUpdateDisclosed,
  startSelfUpdate,
} from './updates.js';

export { getMenubar, setMenubar } from './menubar.js';

export { probeGit, getGithubAccount, startDeviceFlow, getDeviceFlow, pasteGithubToken, signOutGithub } from './githubAccess.js';
