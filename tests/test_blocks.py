import re
from decimal import Decimal

from costpulse.blocks import FOOTER, NAME_WIDTH, NO_SPEND, build_message
from costpulse.costs import ServiceCost

LABEL = "month to date (Oct 1–18)"


def _costs(*pairs):
    return [ServiceCost(name, Decimal(amount)) for name, amount in pairs]


def _table_rows(message):
    body = message["blocks"][1]["text"]["text"]
    return body.strip("`\n").splitlines()


def _parse(row):
    name, amount = row.rsplit(" ", 1)
    return name.strip(), Decimal(amount.strip().lstrip("$").replace(",", ""))


SEVEN = _costs(
    ("Amazon EC2", "6.10"),
    ("Amazon S3", "2.40"),
    ("AmazonCloudWatch", "1.95"),
    ("AWS Lambda", "0.80"),
    ("Amazon Route 53", "0.50"),
    ("AWS Key Management Service", "0.30"),
    ("Amazon DynamoDB", "0.29"),
)


def test_top_5_services_sorted_by_cost_descending():
    rows = [_parse(r) for r in _table_rows(build_message(LABEL, SEVEN))]
    assert [name for name, _ in rows[:5]] == [
        "Amazon EC2",
        "Amazon S3",
        "AmazonCloudWatch",
        "AWS Lambda",
        "Amazon Route 53",
    ]


def test_remaining_services_summed_into_other_row():
    rows = [_parse(r) for r in _table_rows(build_message(LABEL, SEVEN))]
    assert rows[5] == ("Other (2 services)", Decimal("0.59"))
    assert len(rows) == 6


def test_single_leftover_service_uses_singular_noun():
    rows = _table_rows(build_message(LABEL, SEVEN[:6]))
    assert _parse(rows[5])[0] == "Other (1 service)"


def test_fewer_than_5_services_shows_no_other_row():
    rows = _table_rows(build_message(LABEL, SEVEN[:3]))
    assert len(rows) == 3
    assert not any("Other" in r for r in rows)


def test_amounts_are_usd_with_2_decimals_and_total_equals_sum_of_rows():
    costs = _costs(("AWS Lambda", "1234.5"), ("Amazon EC2", "1.005"), ("Amazon S3", "1.005"))
    message = build_message(LABEL, costs)
    rows = [_parse(r) for r in _table_rows(message)]
    header = message["blocks"][0]["text"]["text"]
    total = Decimal(re.search(r"\$([\d,]+\.\d{2})", header).group(1).replace(",", ""))
    # Each 1.005 rounds half-up to 1.01, so the rows sum to 1.01 + 1.01 + 1234.50.
    assert total == sum(amount for _, amount in rows) == Decimal("1236.52")
    assert "$1,234.50" in _table_rows(message)[0]
    assert all(re.search(r"\$[\d,]+\.\d{2}$", r) for r in _table_rows(message))


def test_zero_spend_shows_zero_total_and_no_spend_message():
    message = build_message(LABEL, [])
    assert "*$0.00*" in message["blocks"][0]["text"]["text"]
    assert message["blocks"][1]["text"]["text"] == NO_SPEND


def test_footer_mentions_cost_explorer_delay_and_cache():
    footer = build_message(LABEL, SEVEN)["blocks"][2]["elements"][0]["text"]
    assert footer == FOOTER
    assert "~24h delay" in footer
    assert "cached 1h" in footer


def test_header_shows_label_and_fallback_text_has_total():
    message = build_message(LABEL, SEVEN[:1])
    assert message["blocks"][0]["text"]["text"].startswith(f"*AWS spend · {LABEL}*")
    assert message["text"] == f"AWS spend · {LABEL}: $6.10"


def test_long_service_names_are_truncated_and_columns_align():
    long_name = "Amazon Elastic Compute Cloud - Compute - Extended Name"
    rows = _table_rows(build_message(LABEL, _costs((long_name, "3.00"), ("Amazon S3", "1.00"))))
    assert rows[0].startswith(long_name[: NAME_WIDTH - 1] + "…")
    assert len({len(r) for r in rows}) == 1
