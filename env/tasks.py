"""
Task graders for Cloud-Ops Janitor.

Each grader:
  - Accepts (initial_state: dict, final_state: dict)
  - Returns a float in [0.0, 1.0]
  - Is fully deterministic given the same inputs

Difficulty:  zombie_reaper (easy) → dev_shutdown (medium) → auditor (hard)
"""


# ── Task 1 — Zombie Reaper (Easy) ─────────────────────────────────────────────

def zombie_reaper_grader(initial_state: dict, final_state: dict) -> float:
    """
    Objective: delete every unattached volume older than 30 days.
    Score    : fraction of zombie volumes successfully removed.
    Penalty  : any attached volume that went missing → score = 0.0.
    """
    initial_zombies = [
        v for v in initial_state["volumes"]
        if not v["attached"] and v["age"] > 30
    ]
    remaining_zombies = [
        v for v in final_state["volumes"]
        if not v["attached"] and v["age"] > 30
    ]

    # Integrity check: attached volumes must never be deleted
    initial_safe = {v["id"] for v in initial_state["volumes"] if v["attached"]}
    final_ids    = {v["id"] for v in final_state["volumes"]}
    if initial_safe - final_ids:          # at least one safe volume went missing
        return 0.0

    total = len(initial_zombies)
    if total == 0:
        return 1.0

    deleted = total - len(remaining_zombies)
    return round(deleted / total, 2)


# ── Task 2 — Dev Shutdown (Medium) ────────────────────────────────────────────

def dev_shutdown_grader(initial_state: dict, final_state: dict) -> float:
    """
    Objective: stop every idle dev instance (cpu < 5, status running).
    Score    : fraction of targets correctly stopped.
    Hard penalty: any prod instance stopped → score = 0.0.
    """
    # Immediate disqualification if prod was downed
    prod_down = any(
        i["tag"] == "prod" and i["status"] == "stopped"
        for i in final_state["instances"]
    )
    if prod_down:
        return 0.0

    initial_targets = [
        i for i in initial_state["instances"]
        if i["tag"] == "dev" and i["cpu"] < 5
    ]
    final_stopped = [
        i for i in final_state["instances"]
        if i["tag"] == "dev" and i["cpu"] < 5 and i["status"] == "stopped"
    ]

    total = len(initial_targets)
    if total == 0:
        return 1.0

    return round(len(final_stopped) / total, 2)


# ── Task 3 — Auditor (Hard) ────────────────────────────────────────────────────

def auditor_grader(initial_state: dict, final_state: dict) -> float:
    """
    Objective: simultaneously optimise cost, security, uptime, and integrity.

    Sub-scores (each in [0, 1]):
      cost_score      (0.35) – fraction of *achievable* savings realised
                               (dynamic: based on stoppable devs + deletable zombies)
      security_score  (0.35) – fraction of initially-public DBs now private
      uptime_score    (0.20) – 1.0 unless any prod instance was stopped
      integrity_score (0.10) – 1.0 unless an attached volume was deleted

    The hard task is intentionally multi-objective: maximising cost without
    securing the DB, or securing the DB while destroying uptime, both yield
    partial but not full scores.  A frontier model must balance all four axes.
    """

    # ── Cost score (dynamic divisor, no hardcoded magic number) ────────────
    max_savings = (
        sum(10 for i in initial_state["instances"]
            if i["tag"] == "dev" and i["cpu"] < 5 and i["status"] == "running")
        + sum(5 for v in initial_state["volumes"]
              if not v["attached"] and v["age"] > 30)
    )
    actual_savings = initial_state["cost"] - final_state["cost"]
    cost_score = (
        max(0.0, min(1.0, actual_savings / max_savings))
        if max_savings > 0 else 1.0
    )

    # ── Security score ──────────────────────────────────────────────────────
    initial_public = [db for db in initial_state["databases"] if db["public"]]
    final_public   = [db for db in final_state["databases"]   if db["public"]]
    security_score = (
        1.0 - len(final_public) / len(initial_public)
        if initial_public else 1.0
    )

    # ── Uptime score ────────────────────────────────────────────────────────
    prod_down    = any(i["tag"] == "prod" and i["status"] == "stopped"
                       for i in final_state["instances"])
    uptime_score = 0.0 if prod_down else 1.0

    # ── Integrity score ─────────────────────────────────────────────────────
    initial_attached = {v["id"] for v in initial_state["volumes"] if v["attached"]}
    final_ids        = {v["id"] for v in final_state["volumes"]}
    integrity_score  = 0.0 if (initial_attached - final_ids) else 1.0

    # ── Weighted composite ──────────────────────────────────────────────────
    score = (
        0.35 * cost_score
        + 0.35 * security_score
        + 0.20 * uptime_score
        + 0.10 * integrity_score
    )
    return round(score, 2)
