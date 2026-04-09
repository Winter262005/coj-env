from fastapi import FastAPI, HTTPException
from env.core import CloudEnv
from env.tasks import zombie_reaper_grader, dev_shutdown_grader, auditor_grader
from typing import Optional
from pydantic import BaseModel

app = FastAPI(title="Cloud-Ops Janitor", version="2.0.0")
env = CloudEnv()

GRADERS = {
    "zombie_reaper": zombie_reaper_grader,
    "dev_shutdown":  dev_shutdown_grader,
    "auditor":       auditor_grader,
}


class ActionRequest(BaseModel):
    action_type: str
    target_id: Optional[str] = None


class ResetRequest(BaseModel):
    task: str = "auditor"           # ← which task to set up the episode for


@app.get("/health")
def health():
    return {"status": "ok", "env": "CloudEnv"}


@app.post("/reset")
def reset(request: Optional[ResetRequest] = None):
    """Reset the env for the specified task — each task gets a distinct start state."""
    obs = env.reset(task=request.task)
    env._initial_snapshot = obs
    return obs


@app.post("/step")
def step(action: ActionRequest):
    obs, reward, done, info = env.step(action.model_dump())
    return {"observation": obs, "reward": reward, "done": done, "info": info}


@app.get("/state")
def state():
    return env.state()


@app.get("/grade/{task_name}")
def grade(task_name: str):
    if task_name not in GRADERS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown task '{task_name}'. Valid: {list(GRADERS)}"
        )
    initial = getattr(env, "_initial_snapshot", None)
    if initial is None:
        raise HTTPException(status_code=400, detail="Call /reset before /grade")
    score = GRADERS[task_name](initial, env.state())
    return {"task": task_name, "score": score}


@app.get("/")
def root():
    return {"status": "ok", "docs": "/docs"}


import uvicorn

def main():
    uvicorn.run("server.app:app", host="0.0.0.0", port=7860)

if __name__ == "__main__":
    main()