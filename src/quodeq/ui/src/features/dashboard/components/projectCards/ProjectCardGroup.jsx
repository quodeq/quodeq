import { useState } from 'react';
import { ProjectCard } from './ProjectCard.jsx';
import { CardFooter } from './CardFooter.jsx';
import { ProjectPathContent } from './ProjectPathContent.jsx';
import { ProjectChildren } from './ProjectChildren.jsx';

export function useRelocateDialog(onRelocate) {
  const [relocating, setRelocating] = useState(null);
  const [relocatePath, setRelocatePath] = useState('');
  const startRelocate = (name, currentPath) => { setRelocating(name); setRelocatePath(currentPath || ''); };
  const submitRelocate = (name) => { if (relocatePath.trim()) onRelocate?.(name, relocatePath.trim()); setRelocating(null); };
  return { relocating, relocatePath, setRelocatePath, submitRelocate, setRelocating, startRelocate };
}

// entryLookup (local id/name -> merged entry) lets both this root card and
// its nested subprojects (see ProjectChildren) show their own derived
// chips/action instead of one blanket value for the whole group.
export function ProjectCardGroup({ p, children: childProjects, selectedProject, onSelect, dialogActions, onResumeSetup, publishActions, action, chips, publishedAt, entryLookup }) {
  const { confirmActions, relocateActions } = dialogActions;
  const { confirming, setConfirming, onDelete, onExport } = confirmActions;
  const id = p.id || p.name || p;
  const isSelected = id === selectedProject;
  const hasChildren = !!(childProjects?.[id]?.length);
  const childSelected = hasChildren && childProjects[id].some((c) => (c.id || c.name || c) === selectedProject);
  return (
    <div key={id} className={`project-card-group${childSelected && !isSelected ? ' project-card--child-selected' : ''}`}>
      <ProjectCard project={p} isSelected={isSelected} chips={chips} publishedAt={publishedAt} cardProps={{ onSelect, onResumeSetup, footer: <CardFooter name={id} confirming={confirming} setConfirming={setConfirming} onDelete={onDelete} onExport={onExport} publishActions={publishActions} action={action} /> }}>
        <ProjectPathContent id={id} p={p} relocateActions={relocateActions} subprojectCount={hasChildren ? childProjects[id].length : 0} />
      </ProjectCard>
      {hasChildren && (
        <ProjectChildren
          childList={childProjects[id]}
          selectedProject={selectedProject}
          onSelect={onSelect}
          confirmActions={confirmActions}
          onResumeSetup={onResumeSetup}
          publishActions={publishActions}
          entryLookup={entryLookup}
        />
      )}
    </div>
  );
}
