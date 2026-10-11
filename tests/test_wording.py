"""The fixed status wording (design/design-system.md). Changing a label must fail a test."""

from refdesk.wording import AttributionStatus, RightsStatus, StopReason


def test_rights_wording():
    assert [s.value for s in RightsStatus] == [
        "Open (as stated by source)",
        "Unverified",
        "Permission required",
    ]


def test_attribution_wording():
    assert [s.value for s in AttributionStatus] == [
        "Attribution verified from record",
        "Needs human check",
    ]


def test_every_stop_banner_starts_with_stopped():
    for reason in StopReason:
        assert reason.banner.startswith("Stopped: ")


def test_budget_cap_banner():
    assert StopReason.BUDGET_CAP.banner == "Stopped: budget cap reached"
