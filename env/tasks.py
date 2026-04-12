import math
from env.pricing import INSTANCE_HOURLY


def _clamp01_open(score: float) -> float:
    try:
        s = float(score)
    except (TypeError, ValueError):
        return 0.05
    if not math.isfinite(s):
        return 0.05
    return min(0.99, max(0.01, s))


# ── Task 1: spend_guard ────────────────────────────────────────────────────────

def spend_guard_grader(initial: dict, final: dict) -> float:
    """
    Score = 0.65 * cost_reduction_score + 0.35 * health_score.
    Hard fail (near-zero) if final health < 0.65 (SLA breach).
    Full cost score achieved at >= 35% hourly cost reduction.
    """
    initial_cost = float(initial.get("cost", 0.0))
    final_cost   = float(final.get("cost",   0.0))
    final_health = float(final.get("health", 1.0))

    # Hard SLA check — stopping any high-criticality instance triggers this
    if final_health < 0.65:
        return _clamp01_open(0.02)

    if initial_cost <= 0:
        return _clamp01_open(1.0)

    reduction  = (initial_cost - final_cost) / initial_cost
    cost_score = _clamp01_open(min(1.0, reduction / 0.35))

    # Health score: bonus for staying well above threshold
    health_score = _clamp01_open((final_health - 0.65) / 0.35)

    raw = 0.65 * cost_score + 0.35 * health_score
    return _clamp01_open(raw)


# ── Task 2: compliance_sprint ──────────────────────────────────────────────────

def compliance_sprint_grader(initial: dict, final: dict) -> float:
    """
    Severity-weighted score:  CRITICAL=3pts, HIGH=2pts, MEDIUM=1pt.
    Priority multiplier: all CRITICALs fixed  ->  x1.3
                         any CRITICAL unfixed -> x0.7
    Waste penalty: 0.12 per action wasted on a zombie volume (cost issue, not compliance).

    With 5 steps and 6 issues (2C + 3H + 1M), the optimal strategy is to
    skip the MEDIUM (lowest value) and fix all CRITICALs + HIGHs.
    """
    # Classify initial compliance issues
    init_critical = [db for db in initial.get("databases", []) if db.get("publicly_accessible")]
    init_high     = [v  for v  in initial.get("volumes",   [])
                     if not v.get("encrypted", True) and v.get("state") == "in-use"]
    init_medium   = [i  for i  in initial.get("instances", [])
                     if i.get("tag") == "dev" and i.get("cpu_utilization", 100) < 5
                     and i.get("status") == "running" and not i.get("protected", False)]

    # Classify final state
    final_critical = [db for db in final.get("databases", []) if db.get("publicly_accessible")]
    final_high     = [v  for v  in final.get("volumes",   [])
                      if not v.get("encrypted", True) and v.get("state") == "in-use"]
    final_medium   = [i  for i  in final.get("instances", [])
                      if i.get("tag") == "dev" and i.get("cpu_utilization", 100) < 5
                      and i.get("status") == "running" and not i.get("protected", False)]

    critical_fixed = max(0, len(init_critical) - len(final_critical))
    high_fixed     = max(0, len(init_high)     - len(final_high))
    medium_fixed   = max(0, len(init_medium)   - len(final_medium))

    total_severity = len(init_critical) * 3 + len(init_high) * 2 + len(init_medium) * 1
    if total_severity == 0:
        return _clamp01_open(1.0)

    earned     = critical_fixed * 3 + high_fixed * 2 + medium_fixed * 1
    base_score = earned / total_severity

    # Priority multiplier
    all_criticals_fixed = (critical_fixed == len(init_critical))
    multiplier = 1.3 if all_criticals_fixed else 0.7

    # Waste penalty: zombie volumes deleted (cost action ≠ compliance action)
    initial_zombie_ids = {
        v["id"] for v in initial.get("volumes", [])
        if v.get("state") == "available" and v.get("age", 0) > 30
    }
    final_vol_ids  = {v["id"] for v in final.get("volumes", [])}
    wasted_actions = len(initial_zombie_ids - final_vol_ids)
    waste_penalty  = 0.12 * wasted_actions

    raw = base_score * multiplier - waste_penalty
    return _clamp01_open(raw)


# ── Task 3: rightsizer ─────────────────────────────────────────────────────────

def rightsizer_grader(initial: dict, final: dict) -> float:
    """
    Score correct rightsizing actions (down for overprovisioned, up for underprovisioned).
    Penalise 0.25 per wrong-direction action or per right-sized instance touched.
    """
    final_map = {i["id"]: i for i in final.get("instances", [])}

    init_over  = [i for i in initial.get("instances", []) if i.get("downgrade_target")]
    init_under = [i for i in initial.get("instances", []) if i.get("upgrade_target")]
    init_right = [i for i in initial.get("instances", [])
                  if not i.get("downgrade_target") and not i.get("upgrade_target")]

    total_targets = len(init_over) + len(init_under)
    if total_targets == 0:
        return _clamp01_open(1.0)

    def cost_went_down(init_i: dict) -> bool:
        fi = final_map.get(init_i["id"], {})
        return fi.get("hourly_cost", init_i.get("hourly_cost", 0)) < init_i.get("hourly_cost", 0)

    def cost_went_up(init_i: dict) -> bool:
        fi = final_map.get(init_i["id"], {})
        return fi.get("hourly_cost", init_i.get("hourly_cost", 0)) > init_i.get("hourly_cost", 0)

    def any_change(init_i: dict) -> bool:
        fi = final_map.get(init_i["id"], {})
        return (fi.get("instance_type") != init_i.get("instance_type") or
                fi.get("status")        != init_i.get("status"))

    correct_downs = sum(1 for i in init_over  if cost_went_down(i))
    correct_ups   = sum(1 for i in init_under if cost_went_up(i))

    wrong_actions = (
        sum(1 for i in init_over  if cost_went_up(i))    # upgraded an overprovisioned
        + sum(1 for i in init_under if cost_went_down(i)) # downgraded an underprovisioned
        + sum(1 for i in init_right if any_change(i))     # touched right-sized trap
    )

    correct_score = (correct_downs + correct_ups) / total_targets
    wrong_penalty = wrong_actions * 0.25

    raw = correct_score - wrong_penalty
    return _clamp01_open(raw)


# ── Task 4: cloud_auditor ──────────────────────────────────────────────────────

def cloud_auditor_grader(initial: dict, final: dict) -> float:
    """
    Multi-domain: security (40%) + cost (40%) + integrity (20%).
    Hard fail (near-zero) if:
      - a protected instance was stopped or downgraded
      - a prod instance was stopped
      - an in-use volume was deleted
    """
    final_inst_map = {i["id"]: i for i in final.get("instances", [])}

    # ── Hard fails ───────────────────────────────────────────────────────────
    for i in initial.get("instances", []):
        if i.get("protected", False):
            fi = final_inst_map.get(i["id"], {})
            if (fi.get("status")        != i.get("status") or
                    fi.get("instance_type") != i.get("instance_type")):
                return _clamp01_open(0.0)   # protected resource was touched

    prod_stopped = any(
        i.get("tag") == "prod" and
        final_inst_map.get(i["id"], {}).get("status") == "stopped"
        for i in initial.get("instances", [])
    )
    if prod_stopped:
        return _clamp01_open(0.0)

    init_inuse_ids = {v["id"] for v in initial.get("volumes", []) if v.get("state") == "in-use"}
    final_vol_ids  = {v["id"] for v in final.get("volumes", [])}
    if init_inuse_ids - final_vol_ids:
        return _clamp01_open(0.0)   # attached volume was deleted

    # ── Security score ───────────────────────────────────────────────────────
    init_public  = [db for db in initial.get("databases", []) if db.get("publicly_accessible")]
    final_public = [db for db in final.get("databases",   []) if db.get("publicly_accessible")]
    if not init_public:
        security_score = _clamp01_open(1.0)
    else:
        security_score = _clamp01_open(
            (len(init_public) - len(final_public)) / len(init_public)
        )

    # ── Cost score ───────────────────────────────────────────────────────────
    init_zombies     = [v for v in initial.get("volumes", [])
                        if v.get("state") == "available" and v.get("age", 0) > 30]
    final_zombie_cnt = sum(1 for v in final.get("volumes", [])
                           if v.get("state") == "available" and v.get("age", 0) > 30)
    zombie_score = (_clamp01_open((len(init_zombies) - final_zombie_cnt) / len(init_zombies))
                    if init_zombies else _clamp01_open(1.0))

    init_over = [i for i in initial.get("instances", [])
                 if i.get("downgrade_target") and not i.get("protected", False)]
    correct_downs = sum(
        1 for i in init_over
        if final_inst_map.get(i["id"], {}).get("instance_type") != i.get("instance_type")
    )
    downgrade_score = (_clamp01_open(correct_downs / len(init_over))
                       if init_over else _clamp01_open(1.0))

    cost_score = (zombie_score + downgrade_score) / 2

    # ── Integrity score (already verified above, always 1.0 here) ───────────
    integrity_score = _clamp01_open(1.0)

    raw = 0.40 * security_score + 0.40 * cost_score + 0.20 * integrity_score
    return _clamp01_open(raw)