import base64
import json
import logging
import time
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlencode

import boto3
import pytest
import slack_sdk
from botocore.stub import Stubber
from slack_bolt.adapter.aws_lambda import SlackRequestHandler
from slack_sdk.signature import SignatureVerifier
from slack_sdk.web import SlackResponse
from slack_sdk.webhook import WebhookClient

from costpulse import app as app_module
from costpulse.app import FETCHING, NOT_ENABLED, UNAVAILABLE, create_app
from costpulse.config import Config, load_config, parse_channel_ids
from costpulse.costs import CostUnavailable, ServiceCost
from costpulse.ranges import USAGE

SECRET = "test-signing-secret-0123456789abcdef"
TOKEN = "xoxb-test-token-not-real"
ALLOWED = "C0ALLOWED1"
RESPONSE_URL = "https://hooks.slack.com/commands/T0/1/abc"
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


class FakeContext:
    function_name = "costpulse"
    invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:costpulse"


class FakeLambda:
    def __init__(self):
        self.payloads = []

    def invoke(self, **kwargs):
        self.payloads.append(kwargs["Payload"])
        return {"StatusCode": 202}


class FakeFetcher:
    def __init__(self, costs=None, error=None):
        self.costs = costs or []
        self.error = error
        self.calls = []

    def get_costs(self, date_range):
        self.calls.append(date_range)
        if self.error:
            raise self.error
        return self.costs


def _body(text="", channel_id=ALLOWED):
    return urlencode(
        {
            "command": "/cost",
            "text": text,
            "channel_id": channel_id,
            "team_id": "T0TEAM",
            "user_id": "U0USER",
            "response_url": RESPONSE_URL,
            "trigger_id": "1.2.3",
        }
    )


def _event(body, timestamp=None, secret=SECRET):
    timestamp = str(int(time.time()) if timestamp is None else timestamp)
    signature = SignatureVerifier(secret).generate_signature(timestamp=timestamp, body=body)
    # Function URLs deliver form-encoded bodies base64-encoded.
    return {
        "version": "2.0",
        "headers": {
            "content-type": "application/x-www-form-urlencoded",
            "x-slack-request-timestamp": timestamp,
            "x-slack-signature": signature,
        },
        "body": base64.b64encode(body.encode()).decode(),
        "isBase64Encoded": True,
        "requestContext": {"http": {"method": "POST"}},
    }


@pytest.fixture(autouse=True)
def slack_offline(monkeypatch):
    """Stub the two Slack HTTP calls Bolt makes: auth.test and response_url posts."""
    sent = []

    def auth_test(self, **kwargs):
        return SlackResponse(
            client=self,
            http_verb="POST",
            api_url="https://slack.com/api/auth.test",
            req_args={},
            data={"ok": True, "team_id": "T0TEAM", "user_id": "U0BOT", "bot_id": "B0BOT"},
            headers={},
            status_code=200,
        )

    def send_dict(self, body, headers=None):
        sent.append((self.url, body))

    monkeypatch.setattr(slack_sdk.WebClient, "auth_test", auth_test)
    monkeypatch.setattr(WebhookClient, "send_dict", send_dict)
    return sent


def _run(event, fetcher, allowed=frozenset({ALLOWED})):
    """Handle a request like Lambda would, then replay the async lazy self-invocation."""
    config = Config(signing_secret=SECRET, bot_token=TOKEN, allowed_channel_ids=allowed)
    request_handler = SlackRequestHandler(create_app(config, fetcher, clock=lambda: NOW))
    fake_lambda = FakeLambda()
    request_handler.app.listener_runner.lazy_listener_runner.lambda_client = fake_lambda
    response = request_handler.handle(event, FakeContext())
    for payload in fake_lambda.payloads:
        request_handler.handle(json.loads(payload), FakeContext())
    return response, fake_lambda


def test_bad_signature_returns_401_and_makes_no_aws_call():
    fetcher = FakeFetcher()
    response, fake_lambda = _run(_event(_body(), secret="wrong-secret"), fetcher)
    assert response["statusCode"] == 401
    assert fetcher.calls == []
    assert fake_lambda.payloads == []


def test_timestamp_older_than_5_minutes_returns_401():
    fetcher = FakeFetcher()
    response, _ = _run(_event(_body(), timestamp=int(time.time()) - 301), fetcher)
    assert response["statusCode"] == 401
    assert fetcher.calls == []


def test_channel_not_in_allowlist_gets_ephemeral_hint_and_no_aws_call(slack_offline):
    fetcher = FakeFetcher()
    response, _ = _run(_event(_body(channel_id="C0OTHER")), fetcher)
    assert response["statusCode"] == 200
    assert f"CostPulse only works in <#{ALLOWED}>." in response["body"]
    assert fetcher.calls == []
    assert slack_offline == []


def test_dm_channel_is_rejected(slack_offline):
    fetcher = FakeFetcher()
    response, _ = _run(_event(_body(channel_id="D0DIRECT")), fetcher)
    assert "only works in" in response["body"]
    assert fetcher.calls == []
    assert slack_offline == []


def test_empty_allowlist_rejects_every_command(slack_offline):
    fetcher = FakeFetcher()
    response, _ = _run(_event(_body()), fetcher, allowed=frozenset())
    assert NOT_ENABLED in response["body"]
    assert fetcher.calls == []
    assert slack_offline == []


def test_unknown_argument_gets_ephemeral_usage_hint(slack_offline):
    fetcher = FakeFetcher()
    response, _ = _run(_event(_body(text="banana")), fetcher)
    assert USAGE in response["body"]
    assert fetcher.calls == []
    assert slack_offline == []


def test_valid_command_acks_with_fetching_message():
    response, fake_lambda = _run(_event(_body(text="week")), FakeFetcher())
    assert response["statusCode"] == 200
    assert FETCHING in response["body"]
    assert len(fake_lambda.payloads) == 1


def test_lazy_listener_posts_in_channel_blocks_to_response_url(slack_offline):
    fetcher = FakeFetcher([ServiceCost("Amazon S3", Decimal("2.40"))])
    _run(_event(_body(text="today")), fetcher)
    assert [r.label for r in fetcher.calls] == ["today (Oct 18)"]
    ((url, message),) = slack_offline
    assert url == RESPONSE_URL
    assert message["response_type"] == "in_channel"
    assert "$2.40" in json.dumps(message["blocks"])


def test_cost_explorer_failure_posts_ephemeral_error_without_stack_trace(slack_offline):
    fetcher = FakeFetcher(error=CostUnavailable("LimitExceededException: Rate exceeded"))
    _run(_event(_body()), fetcher)
    ((_, message),) = slack_offline
    assert message["response_type"] == "ephemeral"
    assert message["text"] == UNAVAILABLE
    assert "blocks" not in message


def test_secrets_are_read_from_ssm_once_per_cold_start(monkeypatch):
    loads = []

    def fake_load_config():
        loads.append(1)
        return Config(SECRET, TOKEN, frozenset({ALLOWED}))

    monkeypatch.setattr(app_module, "load_config", fake_load_config)
    monkeypatch.setattr(app_module, "CostFetcher", FakeFetcher)
    app_module._request_handler.cache_clear()
    try:
        bad = _event(_body(), secret="wrong-secret")
        assert app_module.handler(bad, FakeContext())["statusCode"] == 401
        assert app_module.handler(bad, FakeContext())["statusCode"] == 401
    finally:
        app_module._request_handler.cache_clear()
    assert loads == [1]


def test_load_config_reads_both_secrets_from_ssm_with_decryption():
    ssm = boto3.client(
        "ssm", region_name="us-east-1", aws_access_key_id="t", aws_secret_access_key="t"
    )
    with Stubber(ssm) as stubber:
        for name, value in [("/costpulse/sign", SECRET), ("/costpulse/token", TOKEN)]:
            stubber.add_response(
                "get_parameter",
                {"Parameter": {"Name": name, "Value": value, "Type": "SecureString"}},
                {"Name": name, "WithDecryption": True},
            )
        env = {
            "SIGNING_SECRET_PARAM": "/costpulse/sign",
            "BOT_TOKEN_PARAM": "/costpulse/token",
            "ALLOWED_CHANNEL_IDS": f" {ALLOWED} , C0SECOND ,,",
        }
        config = load_config(env, ssm)
    assert config == Config(SECRET, TOKEN, frozenset({ALLOWED, "C0SECOND"}))


def test_missing_allowlist_env_var_means_no_allowed_channels():
    assert parse_channel_ids("") == frozenset()


def test_logs_never_contain_token_signing_secret_or_raw_body(caplog, slack_offline):
    caplog.set_level(logging.DEBUG)
    body = _body(text="month")
    _run(_event(body, secret="wrong-secret"), FakeFetcher())
    _run(_event(body), FakeFetcher([ServiceCost("Amazon S3", Decimal("1.00"))]))
    _run(_event(body), FakeFetcher(error=CostUnavailable("boom")))
    config = Config(SECRET, TOKEN, frozenset({ALLOWED}))
    logs = caplog.text + repr(config)
    assert "Cost Explorer unavailable" in caplog.text
    for forbidden in (SECRET, TOKEN, body, RESPONSE_URL):
        assert forbidden not in logs
