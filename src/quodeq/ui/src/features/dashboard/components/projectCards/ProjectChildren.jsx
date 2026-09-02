import { ProjectCard } from './ProjectCard.jsx';
import { CardFooter } from './CardFooter.jsx';

export function ProjectChildren({ childList, selectedProject, onSelect, confirmActions, onResumeSetup, publishActions, entryLookup }) {
  const { confirming, setConfirming, onDelete, onExport } = confirmActions;
  return (
    <div className="project-children-outer">
      {childList.map((child) => {
        const childId = child.id || child.name || child;
        const childEntry = entryLookup?.get(childId);
        // Origin-URL-matched shared entries never share the child's own id,
        // so child.publishedAt (only set for id matches, see usePublish's
        // publishedAtByProject) misses them -- fall back to the merged
        // entry's shared side.
        const childPublishedAt = child.publishedAt ?? childEntry?.shared?.publishedAt;
        return (
          <div key={childId} className="project-child-entry">
            <ProjectCard
              project={child}
              isSelected={childId === selectedProject}
              chips={childEntry?.chips}
              publishedAt={childPublishedAt}
              cardProps={{
                onSelect, isChild: true, onResumeSetup,
                footer: <CardFooter name={childId} confirming={confirming} setConfirming={setConfirming} onDelete={onDelete} onExport={onExport} publishActions={publishActions} action={childEntry?.action} />,
              }}
            />
          </div>
        );
      })}
    </div>
  );
}
