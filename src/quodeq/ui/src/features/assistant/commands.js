import { t } from '../../strings/index.js';
// Pure helpers for the assistant command layer: meta-command parsing,
// autocomplete matching, and welcome/pill derivation. No React, no network.
// META_COMMANDS mirrors RESERVED_COMMANDS in src/quodeq/assistant/skills.py
// and doubles as the offline fallback when the catalog fetch fails.

// The four built-in meta-command names, referenced by both the catalog
// entries below and buildMetaResponse's dispatch (and, for CLEAR,
// useAssistantComposer's local-only handling of parseMetaCommand's result).
export const META_COMMAND_NAME = Object.freeze({ HELP: 'help', SKILLS: 'skills', ACTIONS: 'actions', CLEAR: 'clear' });

export const META_COMMANDS = [
  { name: META_COMMAND_NAME.HELP, description: t('assistant.cmdHelp') },
  { name: META_COMMAND_NAME.SKILLS, description: t('assistant.cmdSkills') },
  // Still answered locally if typed, but hidden from the welcome list,
  // /help, and autocomplete until the action registry gives it
  // more than one entry. The name stays reserved server-side.
  { name: META_COMMAND_NAME.ACTIONS, description: t('assistant.cmdActions'), hidden: true },
  { name: META_COMMAND_NAME.CLEAR, description: t('assistant.cmdClear') },
];

export const VISIBLE_META_COMMANDS = META_COMMANDS.filter((c) => !c.hidden);

// A padded pill whose skill cannot run in the current scope invites a
// guaranteed-to-fail first tool call, so the view's pill row is capped.
const MAX_PILLS_PER_VIEW = 4;

// Skills the session may offer: read-only (remote) sessions have no
// draft_action server-side, so write-shaped skills would dead-end there.
function offeredSkills(catalog, readOnly) {
  return (catalog?.skills ?? []).filter((s) => !readOnly || !s.requiresWrite);
}

// One skill's line in the /help and /skills listings.
function skillLine(s) {
  return `- \`/${s.name}${s.argumentHint ? ` ${s.argumentHint}` : ''}\` ${s.description}`;
}

export function parseMetaCommand(text) {
  const first = text.trim().split(/\s+/)[0];
  if (!first.startsWith('/')) return null;
  const name = first.slice(1);
  return META_COMMANDS.some((c) => c.name === name) ? name : null;
}

export function matchCommands(catalog, draft, { readOnly = false } = {}) {
  if (!draft.startsWith('/') || /\s/.test(draft)) return [];
  const prefix = draft.slice(1).toLowerCase();
  const skills = offeredSkills(catalog, readOnly)
    .map((s) => ({ name: s.name, description: s.description, argumentHint: s.argumentHint || '' }));
  return [...VISIBLE_META_COMMANDS.map((c) => ({ ...c, argumentHint: '' })), ...skills]
    .filter((c) => c.name.startsWith(prefix));
}

function commandLines(catalog, readOnly) {
  return [
    ...VISIBLE_META_COMMANDS.map((c) => `- \`/${c.name}\` ${c.description}`),
    ...offeredSkills(catalog, readOnly).map(skillLine),
  ].join('\n');
}

export function buildMetaResponse(kind, catalog, { readOnly = false } = {}) {
  if (kind === META_COMMAND_NAME.SKILLS) {
    const skills = offeredSkills(catalog, readOnly);
    if (!skills.length) return t('assistant.noSkillPacks');
    return `**Skills**\n${skills.map(skillLine).join('\n')}`;
  }
  if (kind === META_COMMAND_NAME.ACTIONS) {
    const actions = catalog?.actions ?? [];
    if (!actions.length) return t('assistant.noDraftableActions');
    return `${t('assistant.actionsHeader')}\n${actions.map((a) => `- \`${a.type}\` ${a.description}`).join('\n')}`;
  }
  const intro = readOnly
    ? t('assistant.introReadOnly')
    : t('assistant.intro');
  return `${intro}\n\n**Commands**\n${commandLines(catalog, readOnly)}`;
}

export function pillsForView(catalog, view, { readOnly = false } = {}) {
  if (!view) return [];
  const skills = offeredSkills(catalog, readOnly);
  // Only skills declared for this view: a padded pill whose skill cannot run
  // in the current scope invites a guaranteed-to-fail first tool call.
  return skills
    .filter((s) => (s.views ?? []).includes(view))
    .slice(0, MAX_PILLS_PER_VIEW)
    .map((s) => ({
      label: s.name.replace(/-/g, ' ').replace(/^./, (ch) => ch.toUpperCase()),
      fill: `/${s.name} `,
      description: s.description,
    }));
}
