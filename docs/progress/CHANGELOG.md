# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Project foundation: uv project, ruff, pytest, GitHub Actions CI, PR template.
- SAM template: Lambda (Python 3.14, arm64) with Function URL, explicit least-privilege IAM role, 14-day log retention, `AllowedChannelIds` parameter.
- Tests asserting the IAM role grants only the actions listed in the PRD (NFR3, NFR4, NFR8).
- PRD, milestones and backlog.
- `/cost` argument parsing: `today`, `week` (last 7 days) and `month` (month to date, or the full previous month on the 1st) as UTC date ranges with display labels.
- Cost Explorer query: `UnblendedCost` per service, credits and refunds excluded, paginated, cached in memory for 1 hour; failures raise `CostUnavailable` and are not cached.
- Block Kit reply: top 5 services plus an "Other (N services)" row in an aligned monospace table, total equal to the sum of displayed rows, zero-spend message and data-freshness footer.
- Slack handler on Lambda (Bolt): signature verification, channel allowlist (fail closed), usage hint, ephemeral "Fetching AWS spend…" ack and a lazy self-invocation that posts the in-channel reply via `response_url`. Secrets load from SSM once per cold start; logging capped at WARNING so request bodies never reach CloudWatch.
- `src/requirements.txt` exported from `uv.lock` for `sam build`; CI fails if it drifts.
- Deployed with `sam deploy` and wired as `/cost` in the test workspace; README covers deploy, usage, secret rotation and teardown.
- Cost guardrails: $5 monthly account budget with email alerts (80% actual, 100% forecast), CloudWatch alarm on more than 1,000 invocations in 5 minutes via SNS email, and a documented kill switch (reserved concurrency 0).
