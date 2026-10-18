# CostPulse

A Slack app that answers `/cost` with your AWS spend for today, the last 7 days or month to date, broken down by service.

It runs as a single AWS Lambda behind a Function URL and holds exactly one Slack scope (`commands`) and one AWS data permission (`ce:GetCostAndUsage`). Requirements and design decisions are in [`docs/PRD.md`](docs/PRD.md).

> Status: in development (M1 — foundation). See [`docs/progress/MILESTONES.md`](docs/progress/MILESTONES.md).

## Requirements

- Python 3.14 and [uv](https://docs.astral.sh/uv/)
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) and AWS credentials for the target account
- A Slack workspace where you can create apps

## Develop

```sh
uv sync
uv run ruff check
uv run ruff format --check
uv run pytest
sam validate --lint
```

## Configuration

| Name | Where | Purpose |
|---|---|---|
| `/costpulse/slack-signing-secret` | SSM Parameter Store, `SecureString` | Verifies requests come from Slack |
| `/costpulse/slack-bot-token` | SSM Parameter Store, `SecureString` | Bot token from the Slack app install |
| `AllowedChannelIds` | SAM parameter (`samconfig.toml`) → `ALLOWED_CHANNEL_IDS` | Comma-separated channel IDs where `/cost` works. Empty rejects everything |

Store a secret without it appearing in shell history:

```sh
read -rs SLACK_VALUE && aws ssm put-parameter --region us-east-1 \
  --name /costpulse/slack-signing-secret --type SecureString --value "$SLACK_VALUE" \
  && unset SLACK_VALUE
```

## License

MIT
