# GitHub access

quodeq clones repositories with git. Before every clone it checks, in a few seconds, whether git can reach the address. When it can't, the app shows why and offers ways forward. Users whose git already works never see any of this.

## How quodeq looks for access

1. **Your own git setup.** An SSH key loaded in an agent, or a credential helper with your GitHub login. If `git clone` works for that address in a terminal, it works here.
2. **A GitHub sign-in made in quodeq.** Stored in your system keychain, like AI provider keys. Used only for github.com, only inside the clone process.
3. **Your GitHub CLI login.** If `gh` is installed and logged in, quodeq uses its token. Nothing to configure.

If none of these works, the panel appears.

## The options on the panel

**Sign in with GitHub.** quodeq shows a short code and opens GitHub in your browser. Enter the code, approve quodeq, and the clone continues on its own. Organizations with single sign-on prompt you for your identity provider on GitHub's page. quodeq asks for the `repo` scope, which private clones and publishing results both need.

**Use the GitHub command line.** When `gh` is installed but logged out, run `gh auth login` in a terminal and press "check again".

**Paste a token.** Create a personal access token on GitHub with the `repo` scope and paste it. For organizations with single sign-on, authorize the token for that organization after creating it (classic tokens) or during creation (fine-grained tokens).

**Use your own git setup.** Configure SSH or a credential helper yourself, then press "test again".

## Why "not found" can mean "private"

GitHub answers a private repository you cannot see with "Repository not found" rather than an access error. If you know the repository exists, sign in and try again.

## Other reasons a clone is refused

- **Host key.** Your computer has not trusted this server over SSH before. Run `ssh -T git@<host>` once and accept the host, or use the HTTPS address.
- **Network or timeout.** Check your connection, VPN or proxy.
- **git missing or too old.** quodeq needs git 2.31 or newer.

## Settings

Settings has a "github access" block: your current state, sign in, sign out, and a field to test any repository address. Signing out forgets only the token quodeq stored; it never touches `gh` or your git configuration.

## For forks

The sign-in uses quodeq's public OAuth client id. A fork registers its own OAuth App on GitHub with "Enable Device Flow" on and sets `QUODEQ_GITHUB_CLIENT_ID`.
