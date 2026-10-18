# CostPulse — Product Requirements

> Status: **Locked** (2026-10-18, via `/drill-me`). Changes to scope need a new drill session.

## 1. Overview

CostPulse is a Slack app that answers `/cost` with the AWS account's spend for today, the last 7 days, or month to date, broken down by service. It runs as a single AWS Lambda and holds exactly one Slack scope (`commands`) and one AWS permission (`ce:GetCostAndUsage`).

**Who uses it:** an engineering team (DevOps / SRE / cloud engineers) that wants spend visible in the channel where they already work, without everyone needing AWS console billing access.

**Core problem:** cost is invisible until the monthly bill; checking it means console access most of the team shouldn't have.

**Why it exists now:** it is the deliverable for the Handshake AI Skills Studio mission *Build and Deploy a Custom Slack App*, built to production standards so it also serves as a public portfolio project.

### Handshake mission requirements → how CostPulse meets them

| Mission requirement | CostPulse |
|---|---|
| Own name, description, icon | `CostPulse`, descriptions in §6, original 512×512 icon |
| Only the bot scope(s) its function needs | `commands` only — replies go through `response_url`, so no `chat:write` |
| Slash command wired to a live Request URL that posts a real response to the channel | `/cost` → Lambda Function URL → `in_channel` reply with real Cost Explorer data |
| Real install and test | Installed in personal workspace **StackLab**, tested in `#cloud-cost` |

## 2. Scope

### In scope (v1)

- `/cost [today|week|month]` slash command, default `month`.
- In-channel Block Kit reply: total, top 5 services, "Other (N services)" rollup, data-freshness footer.
- Channel allowlist: the command works only in configured channels.
- Slack request signature verification on every request.
- Deployed with AWS SAM to `us-east-1`; secrets in SSM Parameter Store.
- GitHub Actions CI running lint, format check and tests.

### Out of scope (v1) → v2 candidates

| Feature | Why deferred |
|---|---|
| Scheduled daily digest | Needs `chat:write` — add the scope when the feature exists |
| Spend forecast | Needs a second AWS permission, `ce:GetCostForecast` |
| Anomaly alerts (spike vs 7-day average) | Depends on the digest |
| Per-user restriction beyond channel membership | Channel allowlist covers the v1 need |
| Multi-workspace OAuth distribution / Slack Marketplace | Needs OAuth install flow, token store, landing/privacy/support pages and 10 active workspaces |
| Deploy from CI (GitHub OIDC → AWS) | v1 deploys from the developer's machine |
| Persistent cache (DynamoDB) | In-memory cache is enough at $0.01 per Cost Explorer call |

## 3. User experience

### Happy path

1. A member of `#cloud-cost` types `/cost` (or `/cost today`, `/cost week`).
2. Within 3 seconds they see an ephemeral "Fetching AWS spend…" acknowledgement.
3. A few seconds later, an in-channel message appears for everyone:

```
AWS spend · month to date (Oct 1–17)          $12.34
──────────────────────────────────────────────
EC2 – Compute ............................... $6.10
S3 .......................................... $2.40
CloudWatch .................................. $1.95
Lambda ...................................... $0.80
Route 53 .................................... $0.50
Other (4 services) .......................... $0.59
──────────────────────────────────────────────
Data from Cost Explorer · up to ~24h delay · cached 1h
```

### Edge cases

| Situation | Behaviour |
|---|---|
| Unknown argument (`/cost banana`) | Ephemeral usage hint: `Usage: /cost [today\|week\|month]` |
| Run outside an allowed channel, or in a DM | Ephemeral: `CostPulse only works in <#C…>` (Slack renders the channel name) |
| `ALLOWED_CHANNEL_IDS` empty or unset | Every request rejected (fail closed) |
| `month` on the 1st of the month (UTC) | Shows the previous full month, labelled as such |
| Account spend is $0.00 for the range | Shows `$0.00` with "No spend recorded for this period" |
| Fewer than 5 services | Lists all, no "Other" row |
| Cost Explorer error or throttle | Ephemeral: `Couldn't fetch AWS spend right now — try again in a minute.` Error logged without secrets |
| Unsigned / bad-signature / stale (>5 min) request | HTTP 401, no AWS call |

## 4. Functional requirements

| ID | Requirement |
|---|---|
| FR1 | `/cost` with no argument returns month-to-date spend. |
| FR2 | `/cost today` returns spend for the current UTC day so far. |
| FR3 | `/cost week` returns spend for the last 7 UTC days including today. |
| FR4 | `/cost month` returns spend from the 1st of the current UTC month; on the 1st, the previous full month. |
| FR5 | Arguments are case-insensitive and trimmed; anything else returns the ephemeral usage hint. |
| FR6 | Costs are `UnblendedCost` with `RECORD_TYPE` Credit and Refund excluded (gross usage). |
| FR7 | Reply lists the top 5 services by cost, descending; remaining services are summed into one "Other (N services)" row. |
| FR8 | Amounts are USD, rounded to 2 decimals; the total equals the sum of displayed rows. |
| FR9 | The result reply is `response_type: in_channel`, sent via `response_url`. |
| FR10 | Commands from channels not in `ALLOWED_CHANNEL_IDS` (including DMs) get the ephemeral channel hint and trigger no AWS call. |
| FR11 | Empty or missing `ALLOWED_CHANNEL_IDS` rejects all commands. |
| FR12 | Results are cached in memory per range for 1 hour; a cache hit makes no AWS call. |
| FR13 | Cost Explorer failures produce the ephemeral error message, never a stack trace in Slack. |

## 5. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR1 | **Security — request verification.** Every request's `X-Slack-Signature` is verified with the signing secret; timestamps older than 5 minutes are rejected. Check runs before anything else. |
| NFR2 | **Security — least privilege, Slack.** Exactly one bot scope: `commands`. |
| NFR3 | **Security — least privilege, AWS.** Lambda role allows only `ce:GetCostAndUsage`, `ssm:GetParameter` on the two CostPulse parameters (the AWS-managed `aws/ssm` key policy already permits decryption via SSM), `lambda:InvokeFunction` on itself (lazy listener), and writing to its own log group. No access keys exist. |
| NFR4 | **Secrets.** Signing secret and bot token live in SSM `SecureString` (`/costpulse/slack-signing-secret`, `/costpulse/slack-bot-token`), read once per cold start. Never in git, template, environment variables or logs. |
| NFR5 | **Latency.** Slack receives the acknowledgement in under 3 seconds, including cold starts. |
| NFR6 | **Cost.** Steady-state AWS cost under $1/month: Lambda free tier, free Function URL, free SSM standard parameters, Cost Explorer $0.01/call bounded by the 1-hour cache. |
| NFR7 | **Abuse cap.** Unsigned requests are rejected before any AWS call. Reserved concurrency is not set: the account limit is 10 concurrent executions and AWS requires all 10 to stay unreserved, which also caps concurrency account-wide. Revisit after a quota increase. |
| NFR8 | **Logging.** CloudWatch retention 14 days. Logs never contain the token, signing secret or raw request bodies. |
| NFR9 | **Reproducibility.** All AWS resources defined in `template.yaml`; `sam deploy` creates them and `sam delete` removes them. |

## 6. Slack app identity

| Field | Value |
|---|---|
| Name | CostPulse |
| Short description | Your AWS bill, one slash command away. |
| Long description | Type /cost in any channel to see your AWS spend for today, the last 7 days or month to date, broken down by service. Read-only: it holds a single Slack scope (commands) and a single AWS permission (ce:GetCostAndUsage). |
| Icon | Original pulse-line-over-dollar mark, 512×512 PNG, no AWS or Slack trademarks |
| Background colour | `#0F766E` |
| Bot scopes | `commands` |
| Slash command | `/cost` · hint `[today\|week\|month]` · description "Show AWS spend by service" |
| Request URL | Lambda Function URL output by `sam deploy` |
| Workspace | StackLab (personal, created with a personal email) |
| Allowed channel | `#cloud-cost` (private; CostPulse added to the channel) |

## 7. Architecture

```
Slack (/cost in #cloud-cost)
   │  HTTPS POST, signed
   ▼
Lambda Function URL (auth NONE)
   ▼
CostPulse Lambda — Bolt for Python, process_before_response=True
   ├─ 1. verify signature  ──fail──▶ 401
   ├─ 2. channel allowlist ──fail──▶ ephemeral hint
   ├─ 3. parse argument    ──fail──▶ ephemeral usage
   ├─ 4. ack() "Fetching AWS spend…"   (returns to Slack < 3s)
   └─ 5. lazy listener (async self-invoke)
          ├─ cache hit? ──▶ use it
          ├─ Cost Explorer GetCostAndUsage (us-east-1)
          ├─ format Block Kit
          └─ respond(in_channel) via response_url
SSM Parameter Store ── signing secret + bot token (read at cold start)
```

### Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Language / framework | Python + Slack Bolt (lazy listeners) | Lazy listeners solve the 3-second ack limit on Lambda |
| Compute | AWS Lambda, Function URL | $0, IAM role instead of keys, fits the AWS story |
| Runtime | Python 3.14 (`python3.14`), arm64 | Latest Lambda Python, matches local 3.14; arm64 is cheaper |
| IaC / deploy | AWS SAM (`template.yaml`, `samconfig.toml`) | One readable file; `sam delete` cleans up |
| AWS account / profile | Personal account, CLI profile `default`, `us-east-1` | Cost Explorer API is served from `us-east-1` |
| Secrets | SSM Parameter Store SecureString | Free, not visible in console env vars |
| Allowlist config | SAM parameter → env var `ALLOWED_CHANNEL_IDS` | Not secret; change is a redeploy, so it's audited |
| Cache | In-memory, per range, TTL 1h | No extra infra |
| Tooling | `uv`, `ruff` (lint + format), `pytest` | Matches the global quality gate |
| Repo | Public `shyamenk/costpulse` | The repo link is the Showcase evidence |
| CI | GitHub Actions: ruff check, ruff format --check, pytest | Deploy-from-CI is v2 |

### Repository layout

```
costpulse/
  src/costpulse/
    app.py          # Bolt app + Lambda handler
    ranges.py       # /cost argument -> UTC date range + label
    costs.py        # Cost Explorer query + cache
    blocks.py       # Block Kit formatting
    config.py       # SSM + env loading
  tests/            # unit tests (pytest), named after acceptance criteria
  tests/integration/
  template.yaml
  samconfig.toml
  pyproject.toml
  docs/PRD.md
  docs/progress/{MILESTONES,BACKLOG,CHANGELOG}.md
  .github/workflows/ci.yml
  .github/pull_request_template.md
```

## 8. Testing strategy

- Cost Explorer is stubbed with `botocore.stub.Stubber`; tests never call AWS.
- Handler tests build Slack requests signed with a test signing secret and assert on HTTP status, ack body and `response_url` payload (mocked).
- Date-range logic is tested with a frozen clock, including the 1st of the month and month boundaries.
- Every FR and the security NFRs (NFR1, NFR4, NFR8) have at least one named test; test names map 1:1 to backlog acceptance criteria.

## 9. Milestones

| Milestone | Contents | Depends on |
|---|---|---|
| M1 — Foundation | Repo, uv project, ruff/pytest, CI, PR template, SAM skeleton | — |
| M2 — Core command | Date ranges, Cost Explorer query, Block Kit formatting, cache | M1 |
| M3 — Slack wiring | Bolt handler, signature verification, allowlist, lazy listener, SSM config | M2 |
| M4 — Deploy & install | Slack app config, SSM params, `sam deploy`, Request URL, install in StackLab, live test | M3 |
| M5 — Ship it | README, icon, screenshot, Handshake submission, LinkedIn write-up | M4 |

## 10. Definition of done (v1)

- All FRs and NFRs covered by passing tests; CI green.
- `/cost` works live in StackLab `#cloud-cost` with real AWS data.
- Screenshot of the in-channel reply submitted to Handshake with the Showcase description.
- README documents setup, deploy, `ALLOWED_CHANNEL_IDS`, SSM parameters and teardown.
