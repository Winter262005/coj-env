from pydantic import BaseModel
from typing import List, Optional


class Instance(BaseModel):
    id: str
    cpu: float
    status: str   # "running" | "stopped"
    tag: str      # "dev"    | "prod"


class Volume(BaseModel):
    id: str
    attached: bool
    age: int      # days since creation


class Database(BaseModel):
    id: str
    public: bool  # True = security risk


class Observation(BaseModel):
    instances: List[Instance]
    volumes: List[Volume]
    databases: List[Database]
    cost: float
    health: float
    alerts: List[str] = []


class Action(BaseModel):
    action_type: str          # delete_volume | stop_instance | secure_database | noop
    target_id: Optional[str] = None


class Reward(BaseModel):
    """OpenEnv-spec Reward model (required third typed model)."""
    step_reward: float        # clipped per-step signal  [-1.0, 1.0]
    shaping: float            # potential-based shaping  F(s,s')
    terminal_bonus: float     # end-of-episode bonus (unclipped)
    total: float              # step_reward + terminal_bonus
