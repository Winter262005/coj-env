from pydantic import BaseModel
from typing import List, Optional

class Instance(BaseModel):
    id: str               # e.g., "i-0abcd1234efgh5678"
    instance_type: str    # e.g., "g4dn.xlarge", "m5.large"
    cpu_utilization: float # CloudWatch metric, 0-100%
    status: str           # "running" | "stopped"
    tag: str              # "dev" | "prod"

class Volume(BaseModel):
    id: str               # e.g., "vol-0123456789abcdef0"
    volume_type: str      # e.g., "io2", "gp3"
    state: str            # "available" (unattached) | "in-use" (attached)
    age: int              # days since creation

class Database(BaseModel):
    id: str               # e.g., "rds-postgres-cluster-1"
    publicly_accessible: bool  # True = Security risk (0.0.0.0/0 exposed)

class Observation(BaseModel):
    instances: List[Instance]
    volumes: List[Volume]
    databases: List[Database]
    cost: float           # Approximate hourly AWS bill
    health: float         # 0.0 to 1.0 based on Security Hub / Trusted Advisor
    alerts: List[str] = []

class Action(BaseModel):
    action_type: str      # delete_volume | stop_instance | secure_database | noop
    target_id: Optional[str] = None

class Reward(BaseModel):
    """OpenEnv-spec Reward model."""
    step_reward: float        
    shaping: float            
    terminal_bonus: float     
    total: float