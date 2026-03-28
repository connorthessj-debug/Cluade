"""Shared data models for the badge recognition system."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PersonRecord:
    """Represents a recognized person for badge printing."""
    employee_id: str
    name: str
    department: str = ""
    title: str = ""
    badge_number: str = ""

    def to_dict(self) -> dict:
        return {
            "employee_id": self.employee_id,
            "name": self.name,
            "department": self.department,
            "title": self.title,
            "badge_number": self.badge_number,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PersonRecord":
        return cls(
            employee_id=data["employee_id"],
            name=data["name"],
            department=data.get("department", ""),
            title=data.get("title", ""),
            badge_number=data.get("badge_number", ""),
        )


@dataclass
class RecognitionEvent:
    """A facial recognition match event sent from Pi to server."""
    employee_id: str
    name: str
    department: str
    confidence: float
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    device_id: str = "pi-default"

    def to_dict(self) -> dict:
        return {
            "employee_id": self.employee_id,
            "name": self.name,
            "department": self.department,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "device_id": self.device_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RecognitionEvent":
        return cls(
            employee_id=data["employee_id"],
            name=data["name"],
            department=data.get("department", ""),
            confidence=data["confidence"],
            timestamp=data.get("timestamp", ""),
            device_id=data.get("device_id", "pi-default"),
        )
