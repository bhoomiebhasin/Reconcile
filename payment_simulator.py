"""Local payment simulator for the lost-reply demo. No real payments."""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from recovery_policy import Action, Observation, decide_recovery


@dataclass(frozen=True)
class Charge:
    charge_id: int
    reference: str
    amount_minor: int


class PaymentSimulator:
    """Store charges in a provider-side database without idempotency."""

    def __init__(self, database: Path):
        self.database = database
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS charges (
                    charge_id INTEGER PRIMARY KEY,
                    reference TEXT NOT NULL,
                    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0)
                )
            """)

    def charge(
        self, reference: str, amount_minor: int, *, lose_reply: bool = False
    ) -> Charge:
        if not reference.strip():
            raise ValueError("reference must not be blank")
        if type(amount_minor) is not int or amount_minor <= 0:
            raise ValueError("amount_minor must be a positive integer")

        with closing(sqlite3.connect(self.database)) as connection, connection:
            cursor = connection.execute(
                "INSERT INTO charges (reference, amount_minor) VALUES (?, ?)",
                (reference, amount_minor),
            )
            charge = Charge(cursor.lastrowid, reference, amount_minor)

        if lose_reply:
            raise TimeoutError("Simulated lost reply after commit")
        return charge

    def lookup(self, reference: str) -> list[Charge]:
        with closing(sqlite3.connect(self.database)) as connection:
            rows = connection.execute(
                "SELECT charge_id, reference, amount_minor FROM charges "
                "WHERE reference = ? ORDER BY charge_id",
                (reference,),
            )
            return [Charge(*row) for row in rows]


def classify_charges(charges: list[Charge], expected_amount: int) -> Observation:
    if not charges:
        return Observation.NOT_FOUND
    if len(charges) > 1:
        return Observation.AMBIGUOUS
    if charges[0].amount_minor != expected_amount:
        return Observation.EXECUTED_MISMATCHED
    return Observation.EXECUTED_MATCHING


def run_demo() -> None:
    reference = "invoice-42"
    amount = 499900

    with TemporaryDirectory() as directory:
        baseline = PaymentSimulator(Path(directory) / "baseline.sqlite")
        reconcile = PaymentSimulator(Path(directory) / "reconcile.sqlite")

        try:
            baseline.charge(reference, amount, lose_reply=True)
        except TimeoutError:
            baseline.charge(reference, amount)

        try:
            reconcile.charge(reference, amount, lose_reply=True)
        except TimeoutError:
            charges = reconcile.lookup(reference)
            decision = decide_recovery(
                classify_charges(charges, amount), conclusive=True
            )
            if decision.action is not Action.VERIFY:
                raise RuntimeError(f"Expected an existing charge, got {decision.rule_id}")
            print(f"Recovery decision: {decision.action.value} ({decision.rule_id})")

        print(f"Blind retry: {len(baseline.lookup(reference))} charges")
        print(f"Reconcile:   {len(reconcile.lookup(reference))} charge")


if __name__ == "__main__":
    run_demo()
