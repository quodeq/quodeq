## Getting Started

The first time you launch Quodeq, the onboarding wizard opens automatically. Two screens and you have your first evaluation running.

### The onboarding wizard

1. **Welcome** how quodeq works, and the two ways in: a repository to score, or an evaluations repository to connect.
2. **Analyze** one screen: your repository (a git url or a local folder; for a url, quodeq keeps a working copy in `~/quodeq/repos` unless you change it), the model that reviews it (the one configured in Settings, else the best one found on this machine) and the standard (the quodeq default standard unless you change it). Press **scan and run**.

> **Drafts are saved**
>
> The wizard remembers what you typed. If you close it midway, your draft comes back next time. You can also resume an interrupted setup from the **Projects** tab.

Want to see the welcome again later, even after skipping it? Open **Settings**, find the *onboarding* section and press **show welcome**.

### What happens next

- The **Evaluate** tab streams the run live, including findings as they appear.
- When it finishes, the **Overview** tab opens with grades and top findings.
- **Violations**, **Map**, and **History** let you drill in from different angles.
- To reach your results from another machine or share them with your team, connect an evaluations repository from the **Projects** tab. **import evaluations** restores a previously exported archive.

### Requirements

- **Python 3.12+**. The dashboard UI ships pre-built, so Node.js is not required.
- At least one AI provider configured. See *AI Providers*.
