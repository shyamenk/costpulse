"""Fetch AWS spend by service from Cost Explorer, cached in memory."""

import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from costpulse.ranges import DateRange

CACHE_TTL_SECONDS = 3600
# Gross usage: credits and refunds would net a credit-funded account to $0.00.
EXCLUDE_CREDITS_AND_REFUNDS = {
    "Not": {"Dimensions": {"Key": "RECORD_TYPE", "Values": ["Credit", "Refund"]}}
}


class CostUnavailable(RuntimeError):
    """Cost Explorer could not be reached or rejected the request."""


@dataclass(frozen=True)
class ServiceCost:
    service: str
    amount: Decimal


class CostFetcher:
    def __init__(
        self,
        client: Any = None,
        clock: Callable[[], float] = time.monotonic,
        ttl: float = CACHE_TTL_SECONDS,
    ) -> None:
        # Cost Explorer's API endpoint lives only in us-east-1.
        self._client = client or boto3.client("ce", region_name="us-east-1")
        self._clock = clock
        self._ttl = ttl
        self._cache: dict[tuple, tuple[float, list[ServiceCost]]] = {}

    def get_costs(self, date_range: DateRange) -> list[ServiceCost]:
        """Spend per service for the range, highest first. Zero-cost services are dropped."""
        key = (date_range.start, date_range.end)
        cached = self._cache.get(key)
        if cached and self._clock() - cached[0] < self._ttl:
            return cached[1]

        costs = self._query(date_range)
        self._cache[key] = (self._clock(), costs)
        return costs

    def _query(self, date_range: DateRange) -> list[ServiceCost]:
        totals: dict[str, Decimal] = defaultdict(Decimal)
        request = {
            "TimePeriod": {
                "Start": date_range.start.isoformat(),
                "End": date_range.end.isoformat(),
            },
            "Granularity": "DAILY",
            "Metrics": ["UnblendedCost"],
            "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
            "Filter": EXCLUDE_CREDITS_AND_REFUNDS,
        }
        try:
            while True:
                response = self._client.get_cost_and_usage(**request)
                for day in response["ResultsByTime"]:
                    for group in day["Groups"]:
                        amount = Decimal(group["Metrics"]["UnblendedCost"]["Amount"])
                        totals[group["Keys"][0]] += amount
                token = response.get("NextPageToken")
                if not token:
                    break
                request["NextPageToken"] = token
        except (ClientError, BotoCoreError) as exc:
            raise CostUnavailable(str(exc)) from exc

        costs = [ServiceCost(name, amount) for name, amount in totals.items() if amount != 0]
        return sorted(costs, key=lambda c: (-c.amount, c.service))
