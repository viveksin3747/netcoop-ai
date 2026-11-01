from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

def now():
    return datetime.now(timezone.utc).isoformat()

class Device(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    device_id: str = Field(min_length=1, max_length=80, pattern=r'^[\w.:-]+$')
    device_type: str = Field(default='unknown', max_length=50)
    ip_address: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=100)
    department: str | None = Field(default=None, max_length=100)
    hostel: str | None = Field(default=None, max_length=100)
    segment_id: str | None = Field(default=None, max_length=100)
    services: list[str] = Field(default_factory=list, max_length=30)
    status: Literal['online','offline','unknown'] = 'unknown'
    cpu_usage_percent: float | None = Field(default=None, ge=0, le=100)
    memory_usage_percent: float | None = Field(default=None, ge=0, le=100)
    latency_ms: float | None = Field(default=None, ge=0, le=1e7)
    packet_loss_percent: float | None = Field(default=None, ge=0, le=100)
    jitter_ms: float | None = Field(default=None, ge=0, le=1e7)
    bandwidth_utilization_percent: float | None = Field(default=None, ge=0, le=100)
    interface_errors: int | None = Field(default=None, ge=0)
    dropped_packets: int | None = Field(default=None, ge=0)
    uptime_seconds: float | None = Field(default=None, ge=0)
    temperature_c: float | None = Field(default=None, ge=-100, le=300)

class Connection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_device: str
    target_device: str
    status: Literal['active','down','unknown'] = 'unknown'

class Telemetry(BaseModel):
    model_config = ConfigDict(extra='forbid')
    incident_id: str | None = Field(default=None, max_length=80)
    source_type: Literal['upload','demo','live'] = 'upload'
    data_mode: Literal['simulated','observed'] = 'observed'
    timestamp: datetime
    network_id: str = Field(default='Unspecified network', max_length=100)
    devices: list[Device] = Field(min_length=1, max_length=500)
    connections: list[Connection] = Field(default_factory=list, max_length=1000)
    source_reference: str = Field(default='submitted telemetry', max_length=200)

    @field_validator('timestamp')
    @classmethod
    def timestamp_utc(cls, value):
        if value.tzinfo is None:
            raise ValueError('Timestamp must include timezone, for example 2026-10-31T10:30:00Z')
        if (value - datetime.now(timezone.utc)).total_seconds() > 300:
            raise ValueError('Timestamp is more than five minutes in the future')
        return value.astimezone(timezone.utc)

    @model_validator(mode='after')
    def valid_links(self):
        ids = [d.device_id for d in self.devices]
        if len(ids) != len(set(ids)):
            raise ValueError('Device IDs must be unique')
        for c in self.connections:
            if c.source_device not in ids or c.target_device not in ids:
                raise ValueError('Connections must refer to known device IDs')
        return self

AGENTS = ['performance_agent','infrastructure_agent','connectivity_agent',
          'correlation_agent','recommendation_agent','reporting_agent']
METRICS = ['cpu_usage_percent','memory_usage_percent','latency_ms','packet_loss_percent',
           'jitter_ms','bandwidth_utilization_percent','interface_errors','dropped_packets',
           'temperature_c','uptime_seconds']

class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    cpu_threshold: float = Field(default=85, ge=1, le=100)
    memory_threshold: float = Field(default=90, ge=1, le=100)
    latency_threshold: float = Field(default=100, ge=1, le=10000)
    packet_loss_threshold: float = Field(default=2, ge=0.1, le=100)
    bandwidth_threshold: float = Field(default=85, ge=1, le=100)
    timeout_seconds: float = Field(default=10, ge=0.1, le=60)
    retry_limit: int = Field(default=1, ge=0, le=3)
    stale_after_minutes: int = Field(default=60, ge=1, le=10080)
    enabled_agents: list[str] = Field(default_factory=lambda: AGENTS.copy())

    @field_validator('enabled_agents')
    @classmethod
    def valid_agents(cls, value):
        if any(a not in AGENTS for a in value) or len(value) != len(set(value)):
            raise ValueError('Unknown or duplicate agent')
        return value
