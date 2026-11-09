"""
The policy's money thresholds, as code.

1. When a PO is required (policy §2.1): purchases of EUR 1,000 or above.
2. Who must approve an invoice, by amount (policy §3, "Approval Thresholds").

    | Invoice / PO Value (EUR) | Required Approver                   |
    | Up to 5,000              | Cost Center Owner                   |
    | 5,000.01 – 50,000        | Department Head                     |
    | 50,000.01 – 250,000      | Finance Director                    |
    | Above 250,000            | CFO + Procurement Excellence review |

Why this is code and not left to Claude
---------------------------------------
The bands are in EUR, so a GBP or USD invoice must be converted before its band
is chosen. That conversion can move an invoice across a band (INV-20065 and
INV-20071 are examples). The edges matter too: 5,000.00 and 5,000.01 fall in
different bands. A language model reading a raw number can get either of these
wrong. This function cannot.

Tests (tests/test_approval.py) check that these values still match the policy text.
"""

from __future__ import annotations

from dataclasses import dataclass


# §2.1: "All purchases of goods or services with a value of EUR 1,000 or above require
# an approved Purchase Order". Below this amount, a missing PO is not a policy breach.
PO_REQUIRED_FROM_EUR = 1_000.00


@dataclass(frozen=True)
class ApprovalTier:
    band: str  # the band exactly as written in the policy
    approver: str  # the required approver exactly as written in the policy
    upper_eur: float | None  # inclusive upper edge; None = no upper limit


APPROVAL_TIERS: tuple[ApprovalTier, ...] = (
    ApprovalTier("Up to 5,000", "Cost Center Owner", 5_000.00),
    ApprovalTier("5,000.01 – 50,000", "Department Head", 50_000.00),
    ApprovalTier("50,000.01 – 250,000", "Finance Director", 250_000.00),
    ApprovalTier("Above 250,000", "CFO + Procurement Excellence review", None),
)


def required_approval(amount_eur: float) -> ApprovalTier | None:
    """
    Return the approval tier for an amount in EUR.

    Returns None for zero or negative amounts: those are credit notes, which the
    policy handles through matching (§6.1), not through approval thresholds.
    """
    amount = round(amount_eur, 2)  # policy values are in cents; avoid float noise
    if amount <= 0:
        return None
    for tier in APPROVAL_TIERS:
        if tier.upper_eur is None or amount <= tier.upper_eur:
            return tier
    raise AssertionError("unreachable: the last tier has no upper limit")
