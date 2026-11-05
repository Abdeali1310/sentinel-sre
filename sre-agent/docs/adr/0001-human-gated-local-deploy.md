# Human-gated deployment from the operator's machine

**Status:** accepted

GitHub-hosted runners cannot reach a service running on the operator's laptop, so "the workflow deploys the fix" was never achievable here. The Action therefore only proves the change (lint, tests, image build), while deployment happens locally: the operator passes the Deploy Gate with a chat instruction, and the agent runs a fixed script that pulls `origin/main`, asserts `HEAD == origin/main`, and rebuilds the compose stack. This keeps the deploy observable on camera, keeps the running code provably the merged code, and avoids a self-hosted runner or a cloud target neither of which the incident story needs.

## Considered options

- **Self-hosted GitHub runner on the laptop** — real CI-triggered deploy, but adds a second installer, a token, and a failure mode to a two-day build.
- **Deploy to a free cloud host** — removes the laptop dependency, but the service moves off the machine the agent inspects, and free tiers sleep.
- **`watchtower`-style image polling** — plausible, but the deploy would happen on a timer rather than when a human says so, which weakens the second approval gate the demo is built on.

## Consequences

Base-branch protection cannot prevent deployment of an unmerged branch by itself; the script's `HEAD == origin/main` assertion is what guarantees it. Any future deploy path must preserve that assertion.
