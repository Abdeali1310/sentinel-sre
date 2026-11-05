# The agent commits through the GitHub Git Data API, never `git push`

**Status:** accepted

A fine-grained GitHub token scopes by repository, not by path, so "this token may only touch `payments-api/`" cannot be expressed as a platform permission. The restriction is enforced where the commit is constructed: `publish_fix` reads the changed files from the agent workspace, refuses anything outside `payments-api/app/` and `payments-api/tests/`, and creates blobs → tree → commit → ref through the Git Data API. The agent is never given a `git push` step, so there is no path by which a non-allowlisted file reaches a branch through the normal flow.

## Consequences and the known limitation

Codex runs with a shell tool of its own, so a prompt-injected agent could still attempt `git push` if it could read the token. Mitigations, all of which reduce rather than eliminate the risk: the token is loaded only into the MCP server process and is excluded from Switch's agent environment allowlist; `.env` is untracked; branch protection on `main` blocks direct pushes; CODEOWNERS requires the operator's review on `.github/`, `sre-agent/`, and infrastructure paths. This limitation is stated in the README rather than papered over. If the threat model changes, the upgrade path is a separate machine or container for the MCP server with its own credential boundary.
