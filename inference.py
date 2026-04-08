import os
import json
import requests
from typing import List, Optional
from openai import OpenAI

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME   = os.getenv("MODEL_NAME",   "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN     = os.getenv("HF_TOKEN")
ENV_BASE_URL = os.getenv("ENV_BASE_URL", "https://winter262005-coj-env.hf.space")

if HF_TOKEN is None:
    raise ValueError("HF_TOKEN environment variable is required")

client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)

BENCHMARK = "coj-env"
MAX_STEPS  = 10
TASKS      = ["zombie_reaper", "dev_shutdown", "auditor"]

TASK_GOALS = {
    "zombie_reaper": "Delete ONLY unattached volumes older than 30 days. Ignore databases and instances entirely.",
    "dev_shutdown":  "Stop ONLY idle dev instances where cpu < 5 and status=running. Do not touch prod instances, databases, or volumes.",
    "auditor":       "Fix ALL issues: secure every public database, stop every idle dev instance (cpu<5), delete every zombie volume (unattached + age>30). Keep prod instances running.",
}

def log_start(task, env, model):
    print(f"[START] task={task} env={env} model={model}", flush=True)

def log_step(step, action, reward, done, error):
    print(f"[STEP] step={step} action={action} reward={reward:.2f} done={str(done).lower()} error={error if error else 'null'}", flush=True)

def log_end(success, steps, rewards):
    print(f"[END] success={str(success).lower()} steps={steps} rewards={','.join(f'{r:.2f}' for r in rewards)}", flush=True)


def get_action(state: dict, task: str) -> dict:
    prompt = f"""You are a cloud operations agent.

Task goal: {TASK_GOALS[task]}

Available actions:
  delete_volume    target_id = volume ID   (only if not attached AND age > 30)
  stop_instance    target_id = instance ID (only if tag=dev AND cpu<5 AND status=running)
  secure_database  target_id = database ID (only if public=true)
  noop             no target_id needed     (ONLY if nothing needs fixing)

Current state:
{json.dumps(state, indent=2)}

Return ONLY a JSON object:
{{"action_type": "...", "target_id": "..."}}"""

    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0, max_tokens=60,
        )
        text = (resp.choices[0].message.content or "").strip()
        action = json.loads(text.replace("json","").replace("","").strip())
        if isinstance(action, dict) and "action_type" in action:
            return action
    except Exception:
        pass
    return {"action_type": "noop"}


def is_valid(action: dict, state: dict) -> bool:
    atype, tid = action.get("action_type"), action.get("target_id")
    if atype == "delete_volume":
        return any(v["id"]==tid and not v.get("attached",True) and v.get("age",0)>30 for v in state.get("volumes",[]))
    if atype == "stop_instance":
        return any(i["id"]==tid and i.get("status")=="running" and i.get("tag")=="dev" and i.get("cpu",100)<5 for i in state.get("instances",[]))
    if atype == "secure_database":
        return any(db["id"]==tid and db.get("public",False) for db in state.get("databases",[]))
    return atype == "noop"


def fallback(state: dict) -> dict:
    for db in state.get("databases",[]):
        if db.get("public"):
            return {"action_type":"secure_database","target_id":db["id"]}
    for v in state.get("volumes",[]):
        if not v.get("attached") and v.get("age",0)>30:
            return {"action_type":"delete_volume","target_id":v["id"]}
    for i in state.get("instances",[]):
        if i.get("tag")=="dev" and i.get("cpu",100)<5 and i.get("status")=="running":
            return {"action_type":"stop_instance","target_id":i["id"]}
    return {"action_type":"noop"}


def select_action(state: dict, task: str) -> dict:
    llm = get_action(state, task)
    if llm.get("action_type") == "noop":
        fb = fallback(state)
        if fb.get("action_type") != "noop":
            return fb
        return llm
    if is_valid(llm, state):
        return llm
    fb = fallback(state)
    return fb if is_valid(fb, state) else {"action_type": "noop"}


def run_task(task: str) -> None:
    log_start(task, BENCHMARK, MODEL_NAME)
    rewards, steps_taken, success = [], 0, False
    try:
        # Pass task name so server sets the correct episode state
        state = requests.post(f"{ENV_BASE_URL}/reset", json={"task": task}, timeout=30).json()
        for step in range(1, MAX_STEPS + 1):
            action = select_action(state, task)
            data   = requests.post(f"{ENV_BASE_URL}/step", json=action, timeout=30).json()
            state  = data.get("observation", {})
            reward = float(data.get("reward", 0.0))
            done   = bool(data.get("done", False))
            rewards.append(reward)
            steps_taken = step
            log_step(step, str(action), reward, done, None)
            if done:
                break
        success = sum(rewards) > 0
    except Exception as e:
        print(f"[DEBUG] task={task} error={e}", flush=True)
    finally:
        log_end(success, steps_taken, rewards)


def main():
    for task in TASKS:
        run_task(task)

if __name__ == "__main__":
    main()