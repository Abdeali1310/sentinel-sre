# Sentinel

Sentinel is a closed-loop incident response system: a human team and an AI SRE agent work one incident together in a chat room, from alert to verified fix.

## Language

**Incident**:
An unplanned deviation of the Target Application from expected behavior that requires a human-visible response.
_Avoid_: outage, issue, ticket

**Alert**:
A machine-generated notification that a monitored signal crossed a threshold. Not every Alert becomes an Incident.
_Avoid_: alarm, notification

**Fingerprint**:
The stable identity of an Alert across repeats, used to recognise that two Alerts describe the same problem.
_Avoid_: alert id, hash

**Target Application**:
The Payments API under observation.
_Avoid_: the app, payments service, backend

**Defect**:
A latent flaw in the Target Application that produces incorrect behavior under a specific input or upstream condition.
_Avoid_: bug (reserve for the Jira issue type), flaw

**Fault Trigger**:
An operator-controlled condition that makes a known Defect manifest on demand, so an incident can be rehearsed or demonstrated.
_Avoid_: chaos, demo mode, fake bug

**Symptom**:
The externally observable effect of a Defect, such as a failed checkout.
_Avoid_: error, issue

**Triage**:
Establishing what is broken, how badly, and whether it is already known.
_Avoid_: investigation, first response

**Root Cause**:
The specific code-level reason a Symptom occurs, stated so that a change can remove it.
_Avoid_: reason, cause

**Remediation**:
A change to the Target Application that removes the Root Cause.
_Avoid_: fix, patch, hotfix

**Mitigation**:
A change that reduces an Incident's impact without removing the Root Cause.
_Avoid_: workaround

**Rollback**:
Restoring the previously deployed version of the Target Application.
_Avoid_: revert

**Revert**:
A new commit that undoes the changes of an earlier commit.
_Avoid_: rollback

**Verification**:
Proof, from metrics and Smoke Payments, that the Symptom is gone after deploy.
_Avoid_: confirmation, validation, testing

**Smoke Payment**:
A single checkout request issued solely to confirm the payment path works.
_Avoid_: test, health check

**Resolution**:
The state reached when Verification passes. An Incident is closed only at Resolution.
_Avoid_: fix, done, closure

**Merge Gate**:
The human decision that a proposed change may enter the mainline.
_Avoid_: review, approval

**Deploy Gate**:
The human instruction that merged code may be released.
_Avoid_: release, rollout

**Operator**:
The human with authority to pass the Merge Gate and the Deploy Gate.
_Avoid_: user, admin, approver

**Agent Workspace**:
The checkout the Agent edits while preparing a Remediation.
_Avoid_: clone, repo, sandbox

**Target Checkout**:
The checkout the running system is built from and deployed by.
_Avoid_: main repo, production, server

**Incident Room**:
The chat channel where the Alert, the Agent and the Operators share one transcript.
_Avoid_: channel, group, chat

**Milestone**:
One of the fixed points at which the Agent reports to the Incident Room.
_Avoid_: update, status

**Escalation**:
Handing an Incident back to Operators together with the evidence gathered so far.
_Avoid_: giving up, failure, handoff

**Runbook**:
The documented procedure a responder follows for a known Symptom.
_Avoid_: playbook, SOP

**Closed Loop**:
The property that an Alert leads to a Remediation, a deploy, a Verification and a Resolution, with human gates at merge and deploy, rather than stopping at diagnosis.
_Avoid_: autonomous fix, auto-remediation
