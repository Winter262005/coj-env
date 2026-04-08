"""
Baseline inference script — Cloud-Ops Janitor (COJ-Env)
Root file: inference.py

Required environment variables:
    HF_TOKEN      Hugging Face / API key
    API_BASE_URL  LLM API endpoint  (default: https://router.huggingface.co/v1)
    MODEL_NAME    Model identifier  (default: Qwen/Qwen2.5-72B-Instruct)
    ENV_BASE_URL  Environment URL   (default: deployed HF Space)
"""

import os
import json
import requests
from typing import List, Optional
from openai import OpenAI

# ================= ENV VARIABLES =================
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME   = os.getenv("MODEL_NAME",   "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN     = os.getenv("HF_TOKEN")
ENV_BASE_URL = os.getenv("ENV_BASE_URL", "https://winter262005-coj-env.hf.space")

if HF_TOKEN is None:
    raise ValueError("HF_TOKEN environment variable is required")

# ================= OPENAI CLIENT =================
client = OpenAI(
    base_url=API_BASE_URL,
    api_key=HF_TOKEN,
)

# ================= CONFIG =================
BENCHMARK = "coj-env"
MAX_STEPS = 10
TASKS     = ["zombie_reaper", "dev_shutdown", "auditor"]

TASK_GOALS = {
    "zombie_reaper": "Delete all unattached volumes older than 30 days.",
    "dev_shutdown":  "Stop all idle dev instances (cpu < 5). Never stop prod instances.",
    "auditor":       "Reduce cost, secure all public databases, keep every prod instance running.",
}

# ================= LOGGING =================
def log_start(task: str, env: str, model: str):
    print(f"[START] task={task} env={env} model={model}", flush=True)

def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]):
    error_val = error if error else "null"
    done_val  = str(done).lower()
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )

def log_end(success: bool, steps: int, rewards: List[float]):
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} rewards={rewards_str}",
        flush=True,
    )

# ================= LLM =================
def get_action(state: dict, task: str) -> dict:
    prompt = f"""You are a cloud operations agent.

Task goal: {TASK_GOALS.get(task, "Optimise the cloud environment.")}

Available actions:
  delete_volume    requires target_id (volume ID)
  stop_instance    requires target_id (instance ID)
  secure_database  requires target_id (database ID)
  noop             no target_id needed

Current state:
{json.dumps(state, indent=2)}

Return ONLY valid JSON with no extra text:
{{"action_type": "...", "target_id": "..."}}"""

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=100,
        )
        text    = (response.choices[0].message.content or "").strip()
        cleaned = text.replace("```json", "").replace("```", "").strip()
        action  = json.loads(cleaned)
        if isinstance(action, dict) and "action_type" in action:
            return action
    except Exception:
        pass
    return {"action_type": "noop"}

# ================= VALIDATION =================
def is_valid(action: dict, state: dict) -> bool:
    atype = action.get("action_type")
    tid   = action.get("target_id")

    if atype == "delete_volume":
        for v in state.get("volumes", []):
            if v["id"] == tid:
                return not v.get("attached", True)
        return False

    if atype == "stop_instance":
        for i in state.get("instances", []):
            if i["id"] == tid:
                return i.get("status") == "running"
        return False

    if atype == "secure_database":
        for db in state.get("databases", []):
            if db["id"] == tid:
                return db.get("public", False)
        return False

    return True  # noop or unknown action type

# ================= FALLBACK =================
def fallback(state: dict) -> dict:
    """Deterministic rule-based agent — guarantees a reproducible baseline."""
    for db in state.get("databases", []):
        if db.get("public"):
            return {"action_type": "secure_database", "target_id": db["id"]}
    for v in state.get("volumes", []):
        if not v.get("attached") and v.get("age", 0) > 30:
            return {"action_type": "delete_volume", "target_id": v["id"]}
    for i in state.get("instances", []):
        if i.get("tag") == "dev" and i.get("cpu", 100) < 5 and i.get("status") == "running":
            return {"action_type": "stop_instance", "target_id": i["id"]}
    return {"action_type": "noop"}

# ================= SINGLE TASK RUN =================
def run_task(task: str) -> float:
    """Run one full episode for a given task. Returns the grader score [0.0, 1.0]."""
    log_start(task, BENCHMARK, MODEL_NAME)

    rewards:     List[float] = []
    steps_taken: int         = 0
    success:     bool        = False

    try:
        res   = requests.post(f"{ENV_BASE_URL}/reset", timeout=30)
        state = res.json()

        for step in range(1, MAX_STEPS + 1):
            action = get_action(state, task)

            if not is_valid(action, state):
                action = fallback(state)
            if not is_valid(action, state):
                action = {"action_type": "noop"}

            res  = requests.post(f"{ENV_BASE_URL}/step", json=action, timeout=30)
            data = res.json()

            state  = data.get("observation", {})
            reward = float(data.get("reward", 0.0))
            done   = bool(data.get("done", False))
            error  = data.get("info", {}).get("reason", None)

            rewards.append(reward)
            steps_taken = step

            log_step(step, str(action), reward, done, error)

            if done:
                break

        success = sum(rewards) > 0

    except Exception as e:
        print(f"[DEBUG] task={task} error={e}", flush=True)

    finally:
        log_end(success, steps_taken, rewards)

    # Fetch grader score (separate from structured log — does not alter [END] format)
    score = 0.0
    try:
        grade_res = requests.get(f"{ENV_BASE_URL}/grade/{task}", timeout=10)
        score     = float(grade_res.json().get("score", 0.0))
        print(f"[SCORE] task={task} score={score:.2f}", flush=True)
    except Exception as e:
        print(f"[DEBUG] grader error task={task}: {e}", flush=True)

    return score

# ================= MAIN =================
def main():
    scores = {}
    for task in TASKS:
        scores[task] = run_task(task)
        print()   # blank line between tasks for readability

    # Final summary
    avg = sum(scores.values()) / len(scores)
    print("=" * 48, flush=True)
    print("[RESULTS]", flush=True)
    for task, score in scores.items():
        print(f"  {task:<20} score={score:.2f}", flush=True)
    print(f"  {'average':<20} score={avg:.2f}", flush=True)
    print("=" * 48, flush=True)

# ================= RUN =================
if __name__ == "__main__":
    main()
