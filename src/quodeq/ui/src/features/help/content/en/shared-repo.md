## Shared Repository

A shared repository is a plain git repo your team uses to exchange results. You publish a project's finished runs to it; teammates who connect the same repo see that project in their own list, grades and findings included, without running anything themselves.

### Connecting

Open **Settings**, find the *shared repository* section, paste the repository URL, and press **save**. HTTPS (`https://github.com/team/results.git`) and SSH (`git@github.com:team/results.git`) forms both work.

- An empty repository is fine. The first publish sets up the layout.
- A repository that already contains unrelated files is rejected, so you cannot accidentally point Quodeq at a code repo and write into it.
- If the repo was written by a newer Quodeq than yours, connecting fails with a message asking you to upgrade first.

### Authentication

Quodeq uses your own git setup and never asks for credentials. The rule of thumb: if `git clone` works for that URL in a terminal, it works here.

- **SSH** needs the key loaded in your agent and the host already in `known_hosts`.
- **HTTPS** needs a credential helper holding a token. Interactive prompts are disabled, so a URL that would ask for a password fails instead of hanging.

### Publishing

Once a repo is connected, local project cards grow a **publish** button. It uploads the project's completed runs and flips the card badge to *PUBLISHED*. When a newer run finishes later, the same button reads **update**.

- Only completed runs are published. Interrupted runs, and runs from old Quodeq versions that predate run status tracking, are skipped.
- One publish runs at a time. While it is busy, the other publish buttons wait.
- Each publish records who and when, taken from your git `user.name`. Teammates see it on the card.

### What teammates see

Everyone connected to the same repo gets one merged projects list. Badges tell the entries apart:

| Key | Value |
| --- | --- |
| LOCAL | Exists only on this machine, not published yet. |
| PUBLISHED | A local project that is also in the shared repo. |
| REMOTE | A teammate's project, present only in the shared repo. |

The list renders instantly from the last synced copy, then checks the remote in the background. A sync line in the toolbar shows *syncing…*, *synced* with a time, or *sync failed · retry*; the refresh button forces a new check.

Opening a shared project is read-only. You can browse every run and finding, but evaluating, dismissing findings, and deleting stay local-only. The header shows a *shared · read-only* chip as a reminder.

### Pulling a project

A *REMOTE* card offers **pull local copy**: it imports the project, runs and all, into your local list so you can evaluate it yourself from there. If a local project already has that name, Quodeq asks whether to import it as a copy.

### Disconnecting

**disconnect**, in the same Settings section, forgets the URL and deletes the local cache of the repo. Nothing in the shared repo itself is touched; reconnect later and everything is still there.

> **Where the clone lives**
>
> Quodeq keeps its working clone of the shared repo under `~/.quodeq/cache`. Set `QUODEQ_CACHE_ROOT` to put it somewhere else.
