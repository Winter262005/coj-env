"""
AWS Pricing Reference — us-east-1 on-demand rates ($/hr).
Used across core.py and tasks.py to keep costs consistent.
"""

# ── EC2 Instance Hourly Rates ─────────────────────────────────────────────────
INSTANCE_HOURLY: dict[str, float] = {
    "t3.medium":    0.0416,
    "t3.large":     0.0832,
    "m5.large":     0.0960,
    "m5.xlarge":    0.1920,
    "m5.2xlarge":   0.3840,
    "c6i.2xlarge":  0.3400,
    "c6i.4xlarge":  0.6800,
    "g4dn.medium":  0.2307,
    "g4dn.xlarge":  0.5260,
    "p3.2xlarge":   3.0600,
    "p4d.24xlarge": 32.7700,
}

# ── EBS Volume Hourly Rates (flat proxy @ ~100 GB avg) ───────────────────────
VOLUME_HOURLY: dict[str, float] = {
    "gp3": 0.011,   # $0.08/GB-month × 100 GB / 730 hr
    "io2": 0.017,   # $0.125/GB-month × 100 GB / 730 hr
}

# ── Downgrade Paths: instance_type → cheaper_alternative ─────────────────────
DOWNGRADE_MAP: dict[str, str] = {
    "m5.2xlarge":   "m5.xlarge",
    "m5.xlarge":    "m5.large",
    "c6i.4xlarge":  "c6i.2xlarge",
    "g4dn.xlarge":  "g4dn.medium",
    "p4d.24xlarge": "p3.2xlarge",
}

# ── Upgrade Paths: instance_type → larger_alternative ────────────────────────
UPGRADE_MAP: dict[str, str] = {
    "t3.medium":   "m5.large",
    "m5.large":    "m5.xlarge",
    "g4dn.medium": "g4dn.xlarge",
    "c6i.2xlarge": "c6i.4xlarge",
}


def instance_hourly_cost(instance_type: str) -> float:
    """Return the on-demand hourly cost for a given instance type."""
    return INSTANCE_HOURLY.get(instance_type, 0.10)


def volume_hourly_cost(volume_type: str) -> float:
    """Return the hourly cost proxy for a given EBS volume type."""
    return VOLUME_HOURLY.get(volume_type, 0.011)
