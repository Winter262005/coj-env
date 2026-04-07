import os
import json
import requests
from typing import List, Optional
from openai import OpenAI

# ================= ENV VARIABLES =================
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")  # LLM
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN")

ENV_BASE_URL = os.getenv("ENV_BASE_URL", "https://winter262005-coj-env.hf.space")  # your HF Space

if HF_TOKEN is None:
    raise ValueError("HF_TOKEN environment variable is required")

# ================= OPENAI CLIENT =================
client = OpenAI(
    base_url=API_BASE_URL,
    api_key=HF_TOKEN
)

# ================= CONFIG =================
TASK_NAME = os.getenv("TASK_NAME", "cloud-ops")
BENCHMARK = os.getenv("BENCHMARK", "coj-env")
MAX_STEPS = 10

# ================= LOGGING =================
def log_start(task: str, env: str, model: str):
    print(f"[START] task={task} env={env} model={model}", flush=True)

def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]):
    error_val = error if error else "null"
    done_val = str(done).lower()
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True
    )

def log_end(success: bool, steps: int, rewards: List[float]):
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} rewards={rewards_str}",
        flush=True
    )

# ================= LLM =================
def get_action(state: dict) -> dict:
    prompt = f"""
You are a cloud operations agent.

Goal:
- Fix security issues
- Reduce cost
- Resolve alerts

Available actions:
- delete_volume
- stop_instance
- secure_database
- noop

State:
{state}

Return ONLY JSON:
{{"action_type": "...", "target_id": "..."}}
"""

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=100
        )

        text = (response.choices[0].message.content or "").strip()
        cleaned = text.replace("```json", "").replace("```", "").strip()

        action = json.loads(cleaned)
        if isinstance(action, dict) and "action_type" in action:
            return action

    except Exception:
        pass

    return {"action_type": "noop"}

# ================= VALIDATION =================
def is_valid(action: dict, state: dict) -> bool:
    atype = action.get("action_type")
    tid = action.get("target_id")

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

    return True

# ================= FALLBACK =================
def fallback(state: dict) -> dict:
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

# ================= MAIN =================
def main():
    log_start(TASK_NAME, BENCHMARK, MODEL_NAME)

    rewards = []
    steps_taken = 0
    success = False

    try:
        res = requests.post(f"{ENV_BASE_URL}/reset")
        state = res.json()

        for step in range(1, MAX_STEPS + 1):
            action = get_action(state)

            if not is_valid(action, state):
                action = fallback(state)

            if not is_valid(action, state):
                action = {"action_type": "noop"}

            res = requests.post(f"{ENV_BASE_URL}/step", json=action)
            data = res.json()

            state = data.get("observation", {})
            reward = float(data.get("reward", 0.0))
            done = bool(data.get("done", False))
            error = data.get("error", None)

            rewards.append(reward)
            steps_taken = step

            log_step(step, str(action), reward, done, error)

            if done:
                break

        success = sum(rewards) > 0

    except Exception as e:
        print(f"[DEBUG] error: {e}", flush=True)

    finally:
        log_end(success, steps_taken, rewards)

# ================= RUN =================
if __name__ == "__main__":
    main()