"""Persist observed turn identities and goal metadata, never conversation text."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from hashlib import sha256

from codex_account_manager.adapters.interfaces import GoalInfo
from codex_account_manager.storage.database import connect


def goal_signature(goal: GoalInfo) -> str:
    return json.dumps(
        {
            "present": goal.present,
            "objective_hash": sha256((goal.objective or "").encode()).hexdigest(),
            "budget": goal.token_budget,
        },
        sort_keys=True,
    )


def account_hash(account_id: str) -> str:
    return sha256(account_id.encode()).hexdigest()


@dataclass(frozen=True)
class ObservedWork:
    thread_id: str
    account_hash: str
    turn_status: str
    goal_status: str | None
    goal_present: bool
    limited: bool
    observed_at: float


class WorkTracker:
    async def visible(self) -> list[ObservedWork]:
        async with connect() as db:
            rows = await (
                await db.execute(
                    """SELECT thread_id, account_hash, turn_status, goal_fingerprint,
                goal_status, limited, observed_at FROM observed_work
                WHERE account_hash <> '' AND observed_at >= ?
                ORDER BY observed_at DESC LIMIT 50""",
                    (time.time() - 86400,),
                )
            ).fetchall()
        return [
            ObservedWork(
                thread_id=row[0],
                account_hash=row[1],
                turn_status=row[2],
                goal_status=row[4],
                goal_present=bool(json.loads(row[3])["present"]),
                limited=bool(row[5]),
                observed_at=row[6],
            )
            for row in rows
        ]

    async def ids(self, account_id: str) -> list[str]:
        async with connect() as db:
            await db.execute(
                "DELETE FROM observed_work WHERE observed_at<?", (time.time() - 86400,)
            )
            await db.commit()
            rows = await (
                await db.execute(
                    "SELECT thread_id FROM observed_work WHERE account_hash=? ORDER BY observed_at DESC",
                    (account_hash(account_id),),
                )
            ).fetchall()
        return [row[0] for row in rows]

    async def observe(
        self,
        account_id: str,
        thread_id: str,
        turn: dict | None,
        goal: GoalInfo | None,
        *,
        limited: bool = False,
    ) -> None:
        async with connect() as db:
            row = await (
                await db.execute(
                    "SELECT account_hash, turn_id, turn_status, goal_fingerprint FROM observed_work WHERE thread_id=?",
                    (thread_id,),
                )
            ).fetchone()
            source = account_hash(account_id)
            status = turn.get("status") if turn else None
            turn_id = turn.get("id") if turn else None
            signature = goal_signature(goal) if goal is not None else None
            if row and row[0] != source:
                if status != "inProgress":
                    return
                row = None
            if row and row[2] == "awaitingDesktop" and row[1] == turn_id and status != "inProgress":
                return
            transition = bool(
                limited
                and row
                and row[1] == turn_id
                and row[2] in {"inProgress", "failed", "completed"}
                and row[3] == signature
            )
            if status == "inProgress" and turn_id and signature:
                await db.execute(
                    """INSERT INTO observed_work (
                    thread_id, account_hash, turn_id, turn_status, goal_fingerprint,
                    goal_status, limited, observed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(thread_id) DO UPDATE SET
                    account_hash=excluded.account_hash,
                    turn_id=excluded.turn_id, turn_status=excluded.turn_status,
                    goal_fingerprint=excluded.goal_fingerprint, limited=excluded.limited,
                    goal_status=excluded.goal_status,
                    observed_at=excluded.observed_at""",
                    (
                        thread_id,
                        source,
                        turn_id,
                        status,
                        signature,
                        goal.status if goal else None,
                        0,
                        time.time(),
                    ),
                )
            elif transition:
                await db.execute(
                    """UPDATE observed_work SET turn_status=?, goal_status=?, limited=1,
                    observed_at=?
                    WHERE thread_id=?""",
                    (status, goal.status if goal else None, time.time(), thread_id),
                )
            else:
                await db.execute("DELETE FROM observed_work WHERE thread_id=?", (thread_id,))
            await db.commit()

    async def await_desktop(
        self, source_account: str, target_account: str, thread_ids: list[str]
    ) -> None:
        if not thread_ids:
            return
        async with connect() as db:
            await db.executemany(
                """UPDATE observed_work SET account_hash=?, turn_status='awaitingDesktop',
                limited=0, observed_at=? WHERE account_hash=? AND thread_id=? AND limited=1""",
                [
                    (
                        account_hash(target_account),
                        time.time(),
                        account_hash(source_account),
                        thread_id,
                    )
                    for thread_id in thread_ids
                ],
            )
            await db.commit()

    async def clear(self, account_id: str, thread_ids: list[str]) -> None:
        if not thread_ids:
            return
        async with connect() as db:
            await db.executemany(
                "DELETE FROM observed_work WHERE account_hash=? AND thread_id=?",
                [(account_hash(account_id), thread_id) for thread_id in thread_ids],
            )
            await db.commit()

    async def limited(self, account_id: str) -> list[tuple[str, str, str]]:
        async with connect() as db:
            rows = await (
                await db.execute(
                    """SELECT thread_id, turn_id, goal_fingerprint FROM observed_work
                WHERE account_hash=? AND limited=1 AND observed_at>=?
                ORDER BY observed_at DESC""",
                    (account_hash(account_id), time.time() - 3600),
                )
            ).fetchall()
        return [(row[0], row[1], row[2]) for row in rows]
