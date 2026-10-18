from pathlib import Path

import pytest
import yaml

TEMPLATE = Path(__file__).resolve().parent.parent / "template.yaml"


class _CfnLoader(yaml.SafeLoader):
    pass


def _tag(loader, suffix, node):
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
    else:
        value = loader.construct_mapping(node)
    return {suffix: value}


_CfnLoader.add_multi_constructor("!", _tag)


@pytest.fixture(scope="module")
def resources():
    return yaml.load(TEMPLATE.read_text(), Loader=_CfnLoader)["Resources"]  # noqa: S506


@pytest.fixture(scope="module")
def statements(resources):
    policies = resources["CostPulseRole"]["Properties"]["Policies"]
    assert len(policies) == 1
    return policies[0]["PolicyDocument"]["Statement"]


def test_role_grants_only_expected_actions(statements):
    actions = set()
    for statement in statements:
        assert statement["Effect"] == "Allow"
        action = statement["Action"]
        actions.update(action if isinstance(action, list) else [action])
    assert actions == {
        "ce:GetCostAndUsage",
        "ssm:GetParameter",
        "lambda:InvokeFunction",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
    }


def test_only_cost_explorer_uses_wildcard_resource(statements):
    wildcard = [s["Sid"] for s in statements if s["Resource"] == "*"]
    assert wildcard == ["ReadCosts"]


def test_ssm_access_limited_to_two_costpulse_parameters(statements):
    (ssm,) = [s for s in statements if s["Action"] == "ssm:GetParameter"]
    names = sorted(r["Sub"].rsplit("parameter", 1)[1] for r in ssm["Resource"])
    assert names == ["/costpulse/slack-bot-token", "/costpulse/slack-signing-secret"]


def test_role_has_no_managed_policies(resources):
    assert "ManagedPolicyArns" not in resources["CostPulseRole"]["Properties"]


def test_function_url_is_public_and_function_runs_python_314_arm64(resources):
    props = resources["CostPulseFunction"]["Properties"]
    assert props["FunctionUrlConfig"]["AuthType"] == "NONE"
    assert props["Runtime"] == "python3.14"
    assert props["Architectures"] == ["arm64"]


def test_logs_kept_14_days(resources):
    assert resources["CostPulseLogGroup"]["Properties"]["RetentionInDays"] == 14


def test_secrets_are_parameter_names_not_values(resources):
    env = resources["CostPulseFunction"]["Properties"]["Environment"]["Variables"]
    assert env["SIGNING_SECRET_PARAM"].startswith("/costpulse/")
    assert env["BOT_TOKEN_PARAM"].startswith("/costpulse/")
    assert not any(str(v).startswith("xox") for v in env.values())
