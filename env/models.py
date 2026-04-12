from pydantic import BaseModel
from typing import List, Optional


class Instance(BaseModel):
    id: str                                  # e.g., "i-0abcd1234efgh5678"
    instance_type: str                       # e.g., "g4dn.xlarge", "m5.large"
    cpu_utilization: float                   # CloudWatch metric, 0-100%
    status: str                              # "running" | "stopped"
    tag: str                                 # "dev" | "prod"
    hourly_cost: float = 0.0                 # Real AWS on-demand $/hr
    criticality: str = "medium"             # "high" | "medium" | "low" — SLA impact of stopping
    protected: bool = False                  # If True, agent must NOT stop or downgrade
    downgrade_target: Optional[str] = None  # Cheaper instance type (overprovisioned instances)
    upgrade_target: Optional[str] = None    # Larger instance type (underprovisioned instances)


class Volume(BaseModel):
    id: str               # e.g., "vol-0123456789abcdef0"
    volume_type: str      # e.g., "io2", "gp3"
    state: str            # "available" (unattached) | "in-use" (attached)
    age: int              # days since creation
    hourly_cost: float = 0.0   # Real AWS pricing proxy $/hr
    encrypted: bool = True     # False = HIGH severity compliance issue


class Database(BaseModel):
    id: str                        # e.g., "rds-postgres-cluster-1"
    publicly_accessible: bool      # True = CRITICAL security risk (0.0.0.0/0 exposed)


class Observation(BaseModel):
    instances: List[Instance]
    volumes: List[Volume]
    databases: List[Database]
    cost: float           # Real-time hourly AWS burn rate (sum of running resource costs)
    health: float         # 0.0 to 1.0 — SLA / compliance posture
    alerts: List[str] = []


class Action(BaseModel):
    action_type: str      # delete_volume | stop_instance | secure_database | downgrade_instance | upgrade_instance | encrypt_volume | noop
    target_id: Optional[str] = None


class Reward(BaseModel):
    """OpenEnv-spec Reward model."""
    step_reward: float
    shaping: float
    terminal_bonus: float
    total: float