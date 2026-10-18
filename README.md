# CostPulse

A Slack app that answers `/cost` with your AWS spend for today, the last 7 days or month to date, broken down by service.

It runs as a single AWS Lambda behind a Function URL and holds exactly one Slack scope (`commands`) and one AWS data permission (`ce:GetCostAndUsage`). Requirements and design decisions are in [`docs/PRD.md`](docs/PRD.md).

> Status: deployed and working in a test workspace (M4). See [`docs/progress/MILESTONES.md`](docs/progress/MILESTONES.md).

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
sam build
```

After changing dependencies, regenerate the Lambda requirements file that `sam build` installs (CI fails if it is stale):

```sh
uv export --no-dev --no-hashes --no-emit-project --no-header -q -o src/requirements.txt
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

## Deploy

1. **Create the Slack app** at https://api.slack.com/apps (From scratch). Under **OAuth & Permissions → Bot Token Scopes** add only `commands`, then install it to your workspace.
2. **Store the secrets** in SSM as `SecureString` (see [Configuration](#configuration)): the **Signing Secret** from *Basic Information* and the **Bot User OAuth Token** (`xoxb-…`) from *OAuth & Permissions*.
3. **Set the allowed channels** in `samconfig.toml`:

   ```toml
   parameter_overrides = "AllowedChannelIds=\"C0123456789\""
   ```

   A channel's ID is at the bottom of its *About* tab. For a private channel, add the app to it (`/invite @CostPulse`).
4. **Deploy** (check `aws sts get-caller-identity` points at the right account first):

   ```sh
   sam build
   sam deploy
   ```

   The stack output `RequestUrl` is the Function URL. An unsigned request to it returns `401 {"error": "invalid request"}`.
5. **Create the slash command** under *Slash Commands → Create New Command*: command `/cost`, Request URL = `RequestUrl`, usage hint `[today|week|month]`. Reinstall the app when Slack asks.
6. **Try it**: `/cost`, `/cost today`, `/cost week` in an allowed channel.

### Rotate a secret

Regenerate it in the Slack app settings, overwrite the parameter, then force a cold start so the function reloads it (secrets are read once per cold start):

```sh
read -rs SLACK_VALUE && aws ssm put-parameter --region us-east-1 --overwrite \
  --name /costpulse/slack-signing-secret --type SecureString --value "$SLACK_VALUE" \
  && unset SLACK_VALUE
aws lambda update-function-configuration --region us-east-1 --function-name costpulse \
  --description "secrets rotated $(date -u +%F)"
```

### Tear down

```sh
sam delete --stack-name costpulse
aws ssm delete-parameters --region us-east-1 \
  --names /costpulse/slack-signing-secret /costpulse/slack-bot-token
```

## Usage

| Command | Shows |
|---|---|
| `/cost` or `/cost month` | Month to date (on the 1st: the previous full month) |
| `/cost today` | Today so far (UTC) |
| `/cost week` | Last 7 days including today |

Amounts are gross usage (`UnblendedCost` before credits and refunds): the top 5 services plus an "Other" row. Cost Explorer data lags by up to 24 hours, and results are cached for an hour per range.

## License

MIT
