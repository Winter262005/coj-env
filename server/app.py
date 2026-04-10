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
    task: str = "auditor"


# ── Required OpenEnv API Endpoints ───────────────────────────────────────────

@app.get("/health")
def health():
    # Must return {"status": "healthy"} — "ok" fails openenv validate
    return {"status": "healthy"}


@app.get("/metadata")
def metadata():
    # Required: name (str) and description (str)
    return {
        "name": "cloud-ops-janitor",
        "description": (
            "A reinforcement learning environment for optimizing cloud "
            "infrastructure by removing unused resources, securing databases, "
            "and preserving uptime."
        ),
        "version": "1.0.0",
        "tasks": list(GRADERS.keys()),
    }


@app.get("/schema")
def schema():
    # Required: action (dict), observation (dict), state (dict)
    return {
        "action": {
            "type": "object",
            "properties": {
                "action_type": {
                    "type": "string",
                    "enum": [
                        "delete_volume",
                        "stop_instance",
                        "secure_database",
                        "noop",
                    ],
                },
                "target_id": {"type": "string", "nullable": True},
            },
            "required": ["action_type"],
        },
        "observation": {
            "type": "object",
            "properties": {
                "instances": {"type": "array"},
                "volumes": {"type": "array"},
                "databases": {"type": "array"},
                "cost": {"type": "number"},
                "health": {"type": "number"},
                "alerts": {"type": "array"},
            },
        },
        "state": {
            "type": "object",
            "properties": {
                "instances": {"type": "array"},
                "volumes": {"type": "array"},
                "databases": {"type": "array"},
                "cost": {"type": "number"},
                "health": {"type": "number"},
                "alerts": {"type": "array"},
            },
        },
    }


@app.post("/mcp")
def mcp(payload: Optional[dict] = None):
    # Required: JSON-RPC 2.0 response
    request_id = (payload or {}).get("id", None)
    method = (payload or {}).get("method", "")
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "method": method,
            "status": "ok",
            "description": "Cloud-Ops Janitor MCP endpoint",
        },
    }


# ── Core Environment Endpoints ────────────────────────────────────────────────

@app.post("/reset")
def reset(request: Optional[ResetRequest] = None):
    task = request.task if request else "zombie_reaper"
    env._initial_snapshot = None
    state = env.reset(task=task)
    env._initial_snapshot = state
    return {"observation": state, "reward": None, "done": False}


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
            detail=f"Unknown task '{task_name}'. Valid: {list(GRADERS)}",
        )
    initial = getattr(env, "_initial_snapshot", None)
    if initial is None:
        raise HTTPException(
            status_code=400, detail="Call /reset before /grade"
        )
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