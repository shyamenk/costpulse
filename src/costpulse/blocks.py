"""Format service costs as a Slack Block Kit message."""

from decimal import ROUND_HALF_UP, Decimal

from costpulse.costs import ServiceCost

TOP_N = 5
NAME_WIDTH = 38
FOOTER = "Data from Cost Explorer · up to ~24h delay · cached 1h"
NO_SPEND = "No spend recorded for this period."
CENT = Decimal("0.01")


def build_message(label: str, costs: list[ServiceCost]) -> dict:
    """Return `text` (notification fallback) and `blocks` for a /cost reply.

    `costs` must be sorted highest first, as `CostFetcher.get_costs` returns them.
    """
    rows = [(c.service, _round(c.amount)) for c in costs[:TOP_N]]
    rest = costs[TOP_N:]
    if rest:
        noun = "service" if len(rest) == 1 else "services"
        rows.append(
            (f"Other ({len(rest)} {noun})", sum((_round(c.amount) for c in rest), Decimal()))
        )
    # Total is the sum of displayed (rounded) rows so the message always adds up.
    total = sum((amount for _, amount in rows), Decimal())

    if rows:
        table = "\n".join(f"{_fit(name)} {_usd(amount):>11}" for name, amount in rows)
        body = f"```\n{table}\n```"
    else:
        body = NO_SPEND

    return {
        "text": f"AWS spend · {label}: {_usd(total)}",
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*AWS spend · {label}*\n*{_usd(total)}*"},
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": body}},
            {"type": "context", "elements": [{"type": "mrkdwn", "text": FOOTER}]},
        ],
    }


def _round(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def _usd(amount: Decimal) -> str:
    return f"${amount:,.2f}"


def _fit(name: str) -> str:
    if len(name) > NAME_WIDTH:
        name = name[: NAME_WIDTH - 1] + "…"
    return name.ljust(NAME_WIDTH)
