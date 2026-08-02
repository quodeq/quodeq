import { t } from '../../strings/index.js';
// Pure helpers for the assistant command layer: meta-command parsing,
// autocomplete matching, and welcome/pill derivation. No React, no network.
// META_COMMANDS mirrors RESERVED_COMMANDS in src/quodeq/assistant/skills.py
// and doubles as the offline fallback when the catalog fetch fails.

export const META_COMMANDS = [
  { name: 'help', description: t('assistant.cmdHelp') },
  { name: 'skills', description: t('assistant.cmdSkills') },
  // Still answered locally if typed, but hidden from the welcome list,
  // /help, and autocomplete until the Phase 2 action registry gives it
  // more than one entry. The name stays reserved server-side.
  { name: 'actions', description: t('assistant.cmdActions'), hidden: true },
  { name: 'clear', description: t('assistant.cmdClear') },
];

export const VISIBLE_META_COMMANDS = META_COMMANDS.filter((c) => !c.hidden);

export function parseMetaCommand(text) {
  const first = text.trim().split(/\s+/)[0];
  if (!first.startsWith('/')) return null;
  const name = first.slice(1);
  return META_COMMANDS.some((c) => c.name === name) ? name : null;
}

export function matchCommands(catalog, draft, { readOnly = false } = {}) {
  if (!draft.startsWith('/') || /\s/.test(draft)) return [];
  const prefix = draft.slice(1).toLowerCase();
  // Read-only (remote) sessions have no draft_action server-side, so
  // write-shaped skills would dead-end; hide them from autocomplete too,
  // same rule as pillsForView.
  const skills = (catalog?.skills ?? [])
    .filter((s) => !readOnly || !s.requiresWrite)
    .map((s) => ({ name: s.name, description: s.description, argumentHint: s.argumentHint || '' }));
  return [...VISIBLE_META_COMMANDS.map((c) => ({ ...c, argumentHint: '' })), ...skills]
    .filter((c) => c.name.startsWith(prefix));
}

function commandLines(catalog, readOnly) {
  const skills = (catalog?.skills ?? []).filter((s) => !readOnly || !s.requiresWrite);
  return [
    ...VISIBLE_META_COMMANDS.map((c) => `- \`/${c.name}\` ${c.description}`),
    ...skills.map((s) => `- \`/${s.name}${s.argumentHint ? ` ${s.argumentHint}` : ''}\` ${s.description}`),
  ].join('\n');
}

export function buildMetaResponse(kind, catalog, { readOnly = false } = {}) {
  if (kind === 'skills') {
    const skills = (catalog?.skills ?? []).filter((s) => !readOnly || !s.requiresWrite);
    if (!skills.length) return t('assistant.noSkillPacks');
    return `**Skills**\n${skills.map((s) => `- \`/${s.name}${s.argumentHint ? ` ${s.argumentHint}` : ''}\` ${s.description}`).join('\n')}`;
  }
  if (kind === 'actions') {
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
  // Read-only (remote) sessions have no draft_action server-side, so
  // write-shaped skills would dead-end; hide their pills entirely.
  const skills = (catalog?.skills ?? []).filter((s) => !readOnly || !s.requiresWrite);
  // Only skills declared for this view: a padded pill whose skill cannot run
  // in the current scope invites a guaranteed-to-fail first tool call.
  return skills
    .filter((s) => (s.views ?? []).includes(view))
    .slice(0, 4)
    .map((s) => ({
      label: s.name.replace(/-/g, ' ').replace(/^./, (ch) => ch.toUpperCase()),
      fill: `/${s.name} `,
      description: s.description,
    }));
}
