"""Decide how to recover an action after inspecting the provider."""

from dataclasses import dataclass
from enum import Enum


class Observation(str, Enum):
    EXECUTED_MATCHING = "executed_matching"
    EXECUTED_MISMATCHED = "executed_mismatched"
    NOT_FOUND = "not_found"
    PENDING_EXTERNAL = "pending_external"
    REJECTED_EXTERNAL = "rejected_external"
    AMBIGUOUS = "ambiguous"
    INSPECTION_UNAVAILABLE = "inspection_unavailable"


class Action(str, Enum):
    VERIFY = "verify"
    WAIT = "wait"
    RETRY = "retry"
    FAIL = "fail"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class Decision:
    action: Action
    rule_id: str


def decide_recovery(
    observation: Observation,
    *,
    conclusive: bool,
    has_idempotency_key: bool = False,
    retry_safe_without_key: bool = False,
    can_wait: bool = True,
) -> Decision:
    """Return an auditable decision without dispatching a provider call.

    Set can_wait to False once the inspection budget is exhausted. A caller
    applying RETRY must reuse the original provider key when one exists.
    """
    if observation is Observation.EXECUTED_MISMATCHED:
        return Decision(Action.ESCALATE, "execution_mismatch")
    if observation is Observation.AMBIGUOUS:
        return Decision(Action.ESCALATE, "multiple_matches")

    if conclusive:
        if observation is Observation.EXECUTED_MATCHING:
            return Decision(Action.VERIFY, "execution_matches")
        if observation is Observation.REJECTED_EXTERNAL:
            return Decision(Action.FAIL, "provider_rejected")
        if observation is Observation.NOT_FOUND:
            if has_idempotency_key:
                return Decision(Action.RETRY, "absence_confirmed_reuse_key")
            if retry_safe_without_key:
                return Decision(Action.RETRY, "absence_confirmed_retry_safe")
            return Decision(Action.ESCALATE, "absence_confirmed_retry_unsafe")

    if can_wait:
        return Decision(Action.WAIT, "inspect_again")
    return Decision(Action.ESCALATE, "inspection_budget_exhausted")
