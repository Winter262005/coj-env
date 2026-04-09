"""
Task graders for Cloud-Ops Janitor.

Each grader:
  - Accepts (initial_state: dict, final_state: dict)
  - Returns a float strictly in (0.0, 1.0)
  - Is fully deterministic given the same inputs

Difficulty: zombie_reaper (easy) → dev_shutdown (medium) → auditor (hard)
"""


# ================= HELPER =================
def clamp_score(score: float) -> float:
    """Ensure score is strictly within (0, 1)"""
    return max(0.01, min(0.99, round(score, 2)))


# ── Task 1 — Zombie Reaper (Easy) ─────────────────────────────────────────────

def zombie_reaper_grader(initial_state: dict, final_state: dict) -> float:
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
    final_ids = {v["id"] for v in final_state["volumes"]}

    if initial_safe - final_ids:
        return 0.01  # instead of 0.0

    total = len(initial_zombies)
    if total == 0:
        return 0.99  # instead of 1.0

    deleted = total - len(remaining_zombies)
    return clamp_score(deleted / total)


# ── Task 2 — Dev Shutdown (Medium) ────────────────────────────────────────────

def dev_shutdown_grader(initial_state: dict, final_state: dict) -> float:
    # Immediate disqualification if prod was downed
    prod_down = any(
        i["tag"] == "prod" and i["status"] == "stopped"
        for i in final_state["instances"]
    )
    if prod_down:
        return 0.01  # instead of 0.0

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
        return 0.99  # instead of 1.0

    return clamp_score(len(final_stopped) / total)


# ── Task 3 — Auditor (Hard) ───────────────────────────────────────────────────

def auditor_grader(initial_state: dict, final_state: dict) -> float:

    # ── Cost score ────────────────────────────────────────────────────────
    max_savings = (
        sum(10 for i in initial_state["instances"]
            if i["tag"] == "dev" and i["cpu"] < 5 and i["status"] == "running")
        + sum(5 for v in initial_state["volumes"]
              if not v["attached"] and v["age"] > 30)
    )

    actual_savings = initial_state["cost"] - final_state["cost"]

    if max_savings > 0:
        cost_score = max(0.0, min(1.0, actual_savings / max_savings))
    else:
        cost_score = 1.0

    cost_score = clamp_score(cost_score)

    # ── Security score ─────────────────────────────────────────────────────
    initial_public = [db for db in initial_state["databases"] if db["public"]]
    final_public = [db for db in final_state["databases"] if db["public"]]

    if initial_public:
        security_score = 1.0 - len(final_public) / len(initial_public)
    else:
        security_score = 1.0

    security_score = clamp_score(security_score)

    # ── Uptime score ───────────────────────────────────────────────────────
    prod_down = any(
        i["tag"] == "prod" and i["status"] == "stopped"
        for i in final_state["instances"]
    )
    uptime_score = 0.01 if prod_down else 0.99

    # ── Integrity score ────────────────────────────────────────────────────
    initial_attached = {v["id"] for v in initial_state["volumes"] if v["attached"]}
    final_ids = {v["id"] for v in final_state["volumes"]}

    integrity_score = 0.01 if (initial_attached - final_ids) else 0.99

    # ── Final weighted score ───────────────────────────────────────────────
    score = (
        0.35 * cost_score
        + 0.35 * security_score
        + 0.20 * uptime_score
        + 0.10 * integrity_score
    )

    return clamp_score(score)