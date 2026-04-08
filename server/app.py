from fastapi import FastAPI, HTTPException
from env.core import CloudEnv
from env.tasks import zombie_reaper_grader, dev_shutdown_grader, auditor_grader
from typing import Optional
from pydantic import BaseModel

app = FastAPI(title="Cloud-Ops Janitor", version="1.0.0")
env = CloudEnv()

GRADERS = {
    "zombie_reaper": zombie_reaper_grader,
    "dev_shutdown":  dev_shutdown_grader,
    "auditor":       auditor_grader,
}


class ActionRequest(BaseModel):
    action_type: str
    target_id: Optional[str] = None


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "env": "CloudEnv"}


# ── OpenEnv spec endpoints ────────────────────────────────────────────────────

@app.post("/reset")
def reset():
    obs = env.reset()
    env._initial_snapshot = obs          # stored for /grade
    return obs


@app.post("/step")
def step(action: ActionRequest):
    obs, reward, done, info = env.step(action.model_dump())   # pass dict, not Pydantic obj
    return {"observation": obs, "reward": reward, "done": done, "info": info}


@app.get("/state")
def state():
    return env.state()                   # renamed from get_state()


# ── Grading endpoint ──────────────────────────────────────────────────────────

@app.get("/grade/{task_name}")
def grade(task_name: str):
    """Return a 0.0–1.0 score for the completed episode on the given task."""
    if task_name not in GRADERS:
        raise HTTPException(status_code=404, detail=f"Unknown task '{task_name}'. Valid: {list(GRADERS)}")
    initial = getattr(env, "_initial_snapshot", None)
    if initial is None:
        raise HTTPException(status_code=400, detail="Call /reset before /grade")
    score = GRADERS[task_name](initial, env.state())
    return {"task": task_name, "score": score}


# ── Root ──────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "docs": "/docs"}


# ── Entrypoint ────────────────────────────────────────────────────────────────

import uvicorn

def main():
    uvicorn.run("server.app:app", host="0.0.0.0", port=7860)

if __name__ == "__main__":
    main()
