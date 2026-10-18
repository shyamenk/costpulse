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


@pytest.fixture(scope="module")
def parameters():
    return yaml.load(TEMPLATE.read_text(), Loader=_CfnLoader)["Parameters"]  # noqa: S506


def test_alert_email_is_required_and_feeds_sns_email_subscription(parameters, resources):
    assert "Default" not in parameters["AlertEmail"]
    (subscription,) = resources["AlertTopic"]["Properties"]["Subscription"]
    assert subscription == {"Protocol": "email", "Endpoint": {"Ref": "AlertEmail"}}


def test_alarm_fires_on_over_1000_invocations_in_5_minutes_and_notifies_topic(resources):
    alarm = resources["InvocationSpikeAlarm"]["Properties"]
    assert (alarm["Namespace"], alarm["MetricName"], alarm["Statistic"]) == (
        "AWS/Lambda",
        "Invocations",
        "Sum",
    )
    assert alarm["Dimensions"] == [{"Name": "FunctionName", "Value": {"Ref": "CostPulseFunction"}}]
    assert (alarm["Period"], alarm["EvaluationPeriods"], alarm["Threshold"]) == (300, 1, 1000)
    assert alarm["ComparisonOperator"] == "GreaterThanThreshold"
    assert alarm["TreatMissingData"] == "notBreaching"
    assert alarm["AlarmActions"] == [{"Ref": "AlertTopic"}]


def test_monthly_budget_defaults_to_5_usd_and_emails_on_80_actual_and_100_forecast(
    parameters, resources
):
    assert parameters["MonthlyBudgetUsd"]["Default"] == 5
    props = resources["MonthlyCostBudget"]["Properties"]
    budget = props["Budget"]
    assert (budget["BudgetType"], budget["TimeUnit"]) == ("COST", "MONTHLY")
    assert budget["BudgetLimit"] == {"Amount": {"Ref": "MonthlyBudgetUsd"}, "Unit": "USD"}
    rules = {
        (n["Notification"]["NotificationType"], n["Notification"]["Threshold"]): n["Subscribers"]
        for n in props["NotificationsWithSubscribers"]
    }
    email = [{"SubscriptionType": "EMAIL", "Address": {"Ref": "AlertEmail"}}]
    assert rules == {("ACTUAL", 80): email, ("FORECASTED", 100): email}
