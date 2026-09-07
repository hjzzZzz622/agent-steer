"""Version 1 transport-neutral guidance envelope."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(frozen=True)
class Guidance:
    run_id: str
    text: str
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: str = '1'

    def __post_init__(self):
        for name in ('run_id', 'text', 'id', 'created_at'):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'{name} must be a non-empty string')
        if self.version != '1':
            raise ValueError('unsupported guidance version')
        try:
            stamp = datetime.fromisoformat(self.created_at)
        except ValueError as exc:
            raise ValueError('created_at must be ISO 8601') from exc
        if stamp.tzinfo is None:
            raise ValueError('created_at must include a timezone')

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> 'Guidance':
        if not isinstance(payload, dict) or set(payload) != {
            'run_id', 'text', 'id', 'created_at', 'version'
        }:
            raise ValueError('expected exactly the version 1 envelope fields')
        return cls(**payload)
