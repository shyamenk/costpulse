# Backlog

Test names map 1:1 to acceptance criteria. FR/NFR IDs refer to `docs/PRD.md`.

## M1 — Foundation

### T1 · chore/1-project-foundation · Priority: High · Depends on: none

**What:** Repo, tooling, CI and a SAM template whose IAM role is provably least-privilege.

**Acceptance Criteria:**
- [x] `uv run ruff check`, `uv run ruff format --check` and `uv run pytest` pass locally and in CI
- [x] `sam validate --lint` passes
- [x] Test: role grants only `ce:GetCostAndUsage`, `ssm:GetParameter`, `lambda:InvokeFunction`, `logs:CreateLogStream`, `logs:PutLogEvents` (NFR3) — `test_role_grants_only_expected_actions`
- [x] Test: only the Cost Explorer statement uses `Resource: "*"` — `test_only_cost_explorer_uses_wildcard_resource`
- [x] Test: SSM read limited to the two CostPulse parameters (NFR4) — `test_ssm_access_limited_to_two_costpulse_parameters`
- [x] Test: role has no managed policies — `test_role_has_no_managed_policies`
- [x] Test: Function URL auth NONE, python3.14, arm64 — `test_function_url_is_public_and_function_runs_python_314_arm64`
- [x] Test: log retention 14 days (NFR8) — `test_logs_kept_14_days`
- [x] Test: environment holds parameter names, never secret values (NFR4) — `test_secrets_are_parameter_names_not_values`

**Subtasks:**
- [x] S1: uv project, ruff, pytest, `.gitignore` — depends on: none
- [x] S2: `template.yaml` + `samconfig.toml` — depends on: S1
- [x] S3: template tests — depends on: S2
- [x] S4: CI workflow + PR template — depends on: S1
- [x] S5: public GitHub repo, squash-only, auto-delete branches — depends on: S4

---

## M2 — Core command

### T2 · feat/2-date-ranges · Priority: High · Depends on: T1

**What:** Turn `today|week|month` into UTC Cost Explorer date ranges with display labels.

**Acceptance Criteria:**
- [x] Test: no argument resolves to month (FR1)
- [x] Test: `today` is today 00:00 UTC to tomorrow, exclusive end (FR2)
- [x] Test: `week` covers the last 7 UTC days including today (FR3)
- [x] Test: `month` starts on the 1st of the current UTC month (FR4)
- [x] Test: `month` on the 1st resolves to the full previous month, labelled as such (FR4)
- [x] Test: arguments are trimmed and case-insensitive (FR5)
- [x] Test: unknown argument raises a usage error (FR5)

**Subtasks:**
- [x] S1: `parse_range(text, now)` returning start, end, label — depends on: none
- [x] S2: frozen-clock tests incl. month and year boundaries — depends on: S1

---

### T3 · feat/3-cost-explorer-query · Priority: High · Depends on: T2

**What:** Fetch spend grouped by service for a range, excluding credits and refunds, with a 1-hour in-memory cache.

**Acceptance Criteria:**
- [x] Test: request uses `UnblendedCost`, `GroupBy SERVICE`, and excludes `RECORD_TYPE` Credit and Refund (FR6)
- [x] Test: paginated responses (`NextPageToken`) are summed across pages
- [x] Test: multi-day results are summed per service and sorted highest first
- [x] Test: zero-cost services are dropped
- [x] Test: second call for the same range within 1 hour makes no AWS call (FR12)
- [x] Test: call after 1 hour hits AWS again (FR12)
- [x] Test: Cost Explorer `ClientError` raises a `CostUnavailable` error (FR13)
- [x] Test: failures are not cached

**Subtasks:**
- [x] S1: `get_costs(range)` using boto3 `ce` client in `us-east-1` — depends on: none
- [x] S2: TTL cache keyed by range — depends on: S1
- [x] S3: Stubber-based tests — depends on: S1, S2

---

### T4 · feat/4-block-kit-reply · Priority: High · Depends on: T3

**What:** Format costs as the Block Kit message in PRD §3.

**Acceptance Criteria:**
- [x] Test: top 5 services sorted by cost, descending (FR7)
- [x] Test: remaining services summed into "Other (N services)" (FR7)
- [x] Test: a single leftover service uses the singular "service"
- [x] Test: fewer than 5 services shows no "Other" row (FR7)
- [x] Test: amounts are USD with 2 decimals and the total equals the sum of displayed rows (FR8)
- [x] Test: zero spend shows `$0.00` and "No spend recorded for this period"
- [x] Test: footer mentions Cost Explorer delay and cache
- [x] Test: header shows the range label and the notification fallback text includes the total
- [x] Test: long service names are truncated and columns align

**Subtasks:**
- [x] S1: `build_message(label, costs)` — depends on: none
- [x] S2: tests — depends on: S1

---

## M3 — Slack wiring

### T5 · feat/5-slack-handler · Priority: High · Depends on: T4

**What:** Bolt app on Lambda with signature verification, channel allowlist, lazy listener and SSM-loaded secrets.

**Acceptance Criteria:**
- [ ] Test: request with a bad signature returns 401 and makes no AWS call (NFR1)
- [ ] Test: request with a timestamp older than 5 minutes returns 401 (NFR1)
- [ ] Test: command from a channel not in `ALLOWED_CHANNEL_IDS` gets the ephemeral channel hint and makes no AWS call (FR10)
- [ ] Test: DM channel is rejected (FR10)
- [ ] Test: empty or unset `ALLOWED_CHANNEL_IDS` rejects every command (FR11)
- [ ] Test: unknown argument gets the ephemeral usage hint (FR5)
- [ ] Test: valid command acks with ephemeral "Fetching AWS spend…" (NFR5)
- [ ] Test: lazy listener posts `response_type: in_channel` blocks to `response_url` (FR9)
- [ ] Test: Cost Explorer failure posts the ephemeral error, no stack trace (FR13)
- [ ] Test: secrets are read from SSM once per cold start (NFR4)
- [ ] Test: logs never contain the token, signing secret or raw body (NFR8)

**Subtasks:**
- [ ] S1: `config.py` loading SSM + env — depends on: none
- [ ] S2: `app.py` Bolt app, `process_before_response=True`, lazy listener, `handler` — depends on: S1
- [ ] S3: signed-request test helper — depends on: none
- [ ] S4: handler tests — depends on: S2, S3
- [ ] S5: `src/requirements.txt` exported from `uv.lock` for `sam build` — depends on: S2

---

## M4 — Deploy & install

### T6 · chore/6-deploy-and-install · Priority: High · Depends on: T5

**What:** Deploy to the personal AWS account and wire `/cost` in StackLab.

**Acceptance Criteria:**
- [ ] `sam build` and `sam deploy` succeed; stack outputs `RequestUrl`
- [ ] Unsigned `curl` to the Function URL returns 401
- [ ] `/cost` slash command created with the Request URL, hint `[today|week|month]`
- [ ] App reinstalled; still only the `commands` scope
- [ ] `/cost`, `/cost today`, `/cost week` post correct in-channel replies in `#cloud-cost`
- [ ] `/cost` outside `#cloud-cost` gets the ephemeral channel hint
- [ ] README documents deploy, parameters, SSM setup and `sam delete` teardown

**Subtasks:**
- [ ] S1: `sam build` + `sam deploy` — depends on: none
- [ ] S2: Slack slash command config + reinstall — depends on: S1
- [ ] S3: live test matrix — depends on: S2
- [ ] S4: README — depends on: S3

---

## M5 — Ship it

### T7 · docs/7-ship-handshake · Priority: Medium · Depends on: T6

**What:** Polish and submit to Handshake.

**Acceptance Criteria:**
- [ ] Signing secret regenerated and bot token rotated; SSM updated with `--overwrite`; `/cost` still works
- [ ] Original 512×512 icon uploaded to the Slack app
- [ ] Screenshot of the in-channel reply (no account ID, no secrets visible)
- [ ] Handshake project submitted with repo link, screenshot and ≤500-char description
- [ ] CHANGELOG has a `## [0.1.0]` release section

**Subtasks:**
- [ ] S1: secret rotation — depends on: none
- [ ] S2: icon — depends on: none
- [ ] S3: screenshot + Handshake submission — depends on: S1, S2
