from env.core import CloudEnv

def zombie_reaper_grader(initial_state, final_state):
    # Count orphaned volumes in initial state
    initial_zombies = [
        v for v in initial_state["volumes"]
        if not v["attached"] and v["age"] > 30
    ]

    # Count remaining orphaned volumes in final state
    remaining_zombies = [
        v for v in final_state["volumes"]
        if not v["attached"] and v["age"] > 30
    ]

    total = len(initial_zombies)
    remaining = len(remaining_zombies)

    if total == 0:
        return 1.0  # nothing to do

    deleted = total - remaining

    score = deleted / total
    return round(score, 2)

def dev_shutdown_grader(initial_state, final_state):
    # find target dev instances
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

    stopped = len(final_stopped)

    score = stopped / total
    return round(score, 2)

def auditor_grader(initial_state, final_state):
    # Cost improvement
    initial_cost = initial_state["cost"]
    final_cost = final_state["cost"]

    cost_score = max(0.0, min(1.0, (initial_cost - final_cost) / 20))

    # Security
    initial_insecure = any(db["public"] for db in initial_state.get("databases", []))
    final_secure = all(not db["public"] for db in final_state.get("databases", []))

    security_score = 1.0 if initial_insecure and final_secure else 0.0

    # Uptime
    prod_down = any(
        i["tag"] == "prod" and i["status"] == "stopped"
        for i in final_state.get("instances", [])
    )

    uptime_score = 0.0 if prod_down else 1.0

    # Final weighted score
    score = (
        0.4 * cost_score +
        0.4 * security_score +
        0.2 * uptime_score
    )

    return round(score, 2)