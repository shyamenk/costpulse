from datetime import date
from decimal import Decimal

import boto3
import pytest
from botocore.stub import ANY, Stubber

from costpulse.costs import CostFetcher, CostUnavailable, ServiceCost
from costpulse.ranges import DateRange

RANGE = DateRange(date(2026, 10, 12), date(2026, 10, 19), "last 7 days (Oct 12–18)")


def _group(service, amount):
    return {"Keys": [service], "Metrics": {"UnblendedCost": {"Amount": amount, "Unit": "USD"}}}


def _day(start, *groups):
    return {
        "TimePeriod": {"Start": start, "End": start},
        "Total": {},
        "Groups": list(groups),
        "Estimated": False,
    }


def _response(*days, token=None):
    response = {"ResultsByTime": list(days), "DimensionValueAttributes": []}
    if token:
        response["NextPageToken"] = token
    return response


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def ce():
    client = boto3.client(
        "ce",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    with Stubber(client) as stubber:
        yield client, stubber
        stubber.assert_no_pending_responses()


@pytest.fixture
def clock():
    return FakeClock()


def test_request_uses_unblended_cost_grouped_by_service_excluding_credits_and_refunds(ce, clock):
    client, stubber = ce
    stubber.add_response(
        "get_cost_and_usage",
        _response(_day("2026-10-12", _group("Amazon S3", "1.50"))),
        {
            "TimePeriod": {"Start": "2026-10-12", "End": "2026-10-19"},
            "Granularity": "DAILY",
            "Metrics": ["UnblendedCost"],
            "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
            "Filter": {
                "Not": {"Dimensions": {"Key": "RECORD_TYPE", "Values": ["Credit", "Refund"]}}
            },
        },
    )
    assert CostFetcher(client, clock).get_costs(RANGE) == [
        ServiceCost("Amazon S3", Decimal("1.50"))
    ]


def test_paginated_responses_are_summed_across_pages(ce, clock):
    client, stubber = ce
    stubber.add_response(
        "get_cost_and_usage",
        _response(_day("2026-10-12", _group("AWS Lambda", "0.25")), token="page-2"),
    )
    stubber.add_response(
        "get_cost_and_usage",
        _response(_day("2026-10-13", _group("AWS Lambda", "0.75"))),
        {
            "TimePeriod": ANY,
            "Granularity": ANY,
            "Metrics": ANY,
            "GroupBy": ANY,
            "Filter": ANY,
            "NextPageToken": "page-2",
        },
    )
    assert CostFetcher(client, clock).get_costs(RANGE) == [
        ServiceCost("AWS Lambda", Decimal("1.00"))
    ]


def test_multi_day_results_are_summed_per_service_and_sorted_highest_first(ce, clock):
    client, stubber = ce
    stubber.add_response(
        "get_cost_and_usage",
        _response(
            _day("2026-10-12", _group("Amazon S3", "1.00"), _group("Amazon EC2", "2.00")),
            _day("2026-10-13", _group("Amazon S3", "0.40"), _group("Amazon EC2", "3.10")),
        ),
    )
    assert CostFetcher(client, clock).get_costs(RANGE) == [
        ServiceCost("Amazon EC2", Decimal("5.10")),
        ServiceCost("Amazon S3", Decimal("1.40")),
    ]


def test_zero_cost_services_are_dropped(ce, clock):
    client, stubber = ce
    stubber.add_response(
        "get_cost_and_usage",
        _response(_day("2026-10-12", _group("Tax", "0"), _group("Amazon S3", "0.01"))),
    )
    assert CostFetcher(client, clock).get_costs(RANGE) == [
        ServiceCost("Amazon S3", Decimal("0.01"))
    ]


def test_second_call_for_same_range_within_an_hour_makes_no_aws_call(ce, clock):
    client, stubber = ce
    stubber.add_response(
        "get_cost_and_usage", _response(_day("2026-10-12", _group("Amazon S3", "1.00")))
    )
    fetcher = CostFetcher(client, clock)
    first = fetcher.get_costs(RANGE)
    clock.now += 3599
    # Stubber raises if a second, unqueued AWS call is made.
    assert fetcher.get_costs(RANGE) == first


def test_call_after_an_hour_hits_aws_again(ce, clock):
    client, stubber = ce
    stubber.add_response(
        "get_cost_and_usage", _response(_day("2026-10-12", _group("Amazon S3", "1.00")))
    )
    stubber.add_response(
        "get_cost_and_usage", _response(_day("2026-10-12", _group("Amazon S3", "2.00")))
    )
    fetcher = CostFetcher(client, clock)
    fetcher.get_costs(RANGE)
    clock.now += 3600
    assert fetcher.get_costs(RANGE) == [ServiceCost("Amazon S3", Decimal("2.00"))]


def test_cost_explorer_client_error_raises_cost_unavailable(ce, clock):
    client, stubber = ce
    stubber.add_client_error("get_cost_and_usage", "LimitExceededException", "Rate exceeded")
    with pytest.raises(CostUnavailable):
        CostFetcher(client, clock).get_costs(RANGE)


def test_failures_are_not_cached(ce, clock):
    client, stubber = ce
    stubber.add_client_error("get_cost_and_usage", "LimitExceededException", "Rate exceeded")
    stubber.add_response(
        "get_cost_and_usage", _response(_day("2026-10-12", _group("Amazon S3", "1.00")))
    )
    fetcher = CostFetcher(client, clock)
    with pytest.raises(CostUnavailable):
        fetcher.get_costs(RANGE)
    assert fetcher.get_costs(RANGE) == [ServiceCost("Amazon S3", Decimal("1.00"))]
