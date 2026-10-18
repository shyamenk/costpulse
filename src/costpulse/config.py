"""Runtime configuration: Slack secrets from SSM, channel allowlist from the environment."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import boto3


@dataclass(frozen=True)
class Config:
    # repr=False keeps secrets out of logs and tracebacks that print the config.
    signing_secret: str = field(repr=False)
    bot_token: str = field(repr=False)
    allowed_channel_ids: frozenset[str]


def parse_channel_ids(raw: str) -> frozenset[str]:
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def load_config(env: Mapping[str, str] = os.environ, ssm: Any = None) -> Config:
    ssm = ssm or boto3.client("ssm")

    def secret(name: str) -> str:
        return ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]

    return Config(
        signing_secret=secret(env["SIGNING_SECRET_PARAM"]),
        bot_token=secret(env["BOT_TOKEN_PARAM"]),
        allowed_channel_ids=parse_channel_ids(env.get("ALLOWED_CHANNEL_IDS", "")),
    )
