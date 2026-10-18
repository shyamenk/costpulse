"""Slack entry point: the /cost command on AWS Lambda."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from functools import cache

from slack_bolt import App
from slack_bolt.adapter.aws_lambda import SlackRequestHandler

from costpulse.blocks import build_message
from costpulse.config import Config, load_config
from costpulse.costs import CostFetcher, CostUnavailable
from costpulse.ranges import UsageError, parse_range

FETCHING = "Fetching AWS spend…"
UNAVAILABLE = "Couldn't fetch AWS spend right now — try again in a minute."
NOT_ENABLED = "CostPulse isn't enabled in any channel yet."

logger = logging.getLogger("costpulse")
# Bolt logs full request bodies at INFO/DEBUG (e.g. on a bad signature); keep them out of logs.
logger.setLevel(logging.WARNING)


def create_app(
    config: Config,
    fetcher: CostFetcher,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> App:
    app = App(
        token=config.bot_token,
        signing_secret=config.signing_secret,
        process_before_response=True,
        token_verification_enabled=False,
        logger=logger,
    )

    def rejection(command: dict) -> str | None:
        """Ephemeral reason the command can't run, or None if it can."""
        if command.get("channel_id") not in config.allowed_channel_ids:
            if not config.allowed_channel_ids:
                return NOT_ENABLED
            channels = " or ".join(f"<#{c}>" for c in sorted(config.allowed_channel_ids))
            return f"CostPulse only works in {channels}."
        try:
            parse_range(command.get("text", ""), clock())
        except UsageError as exc:
            return str(exc)
        return None

    def ack_cost(ack, command):
        ack(rejection(command) or FETCHING)

    def post_cost(respond, command):
        # Lazy listeners run after every ack, including rejections.
        if rejection(command):
            return
        date_range = parse_range(command.get("text", ""), clock())
        try:
            costs = fetcher.get_costs(date_range)
        except CostUnavailable as exc:
            logger.warning("Cost Explorer unavailable: %s", exc)
            respond(text=UNAVAILABLE, response_type="ephemeral", replace_original=False)
            return
        respond(response_type="in_channel", **build_message(date_range.label, costs))

    app.command("/cost")(ack=ack_cost, lazy=[post_cost])
    return app


@cache
def _request_handler() -> SlackRequestHandler:
    # Built once per Lambda container, so SSM is read once per cold start.
    return SlackRequestHandler(create_app(load_config(), CostFetcher()))


def handler(event, context):
    return _request_handler().handle(event, context)
