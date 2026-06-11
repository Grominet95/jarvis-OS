"""
JobTracker — suivi des candidatures stages/jobs.
Stockage JSON dans memory_data/jobs.json.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

from jarvis.kernel.settings import settings


class JobStatus(StrEnum):
    APPLIED = "applied"
    WAITING = "waiting"
    INTERVIEW = "interview"
    REJECTED = "rejected"
    OFFER = "offer"
    ACCEPTED = "accepted"


@dataclass
class JobApplication:
    id: str
    company: str
    role: str
    status: JobStatus
    applied_at: str  # ISO date string
    notes: str = ""
    contact: str = ""
    url: str = ""
    next_step: str = ""
    next_step_date: str = ""

    def days_since_applied(self) -> int:
        try:
            applied = date.fromisoformat(self.applied_at[:10])
            return (date.today() - applied).days
        except Exception:
            return 0

    def is_pending(self) -> bool:
        return self.status in (JobStatus.APPLIED, JobStatus.WAITING)


def _jobs_path() -> Path:
    return Path(settings.memory_dir) / "jobs.json"


class JobTracker:
    def load(self) -> list[JobApplication]:
        path = _jobs_path()
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return [JobApplication(**item) for item in data]
        except Exception:
            return []

    def save_all(self, apps: list[JobApplication]) -> None:
        path = _jobs_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([asdict(a) for a in apps], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add(self, company: str, role: str, notes: str = "", url: str = "") -> JobApplication:
        app = JobApplication(
            id=f"job_{uuid.uuid4().hex[:8]}",
            company=company,
            role=role,
            status=JobStatus.APPLIED,
            applied_at=datetime.now().isoformat(),
            notes=notes,
            url=url,
        )
        apps = self.load()
        apps.append(app)
        self.save_all(apps)
        return app

    def update_status(
        self, company: str, status: JobStatus, notes: str = ""
    ) -> JobApplication | None:
        apps = self.load()
        # Cherche par nom d'entreprise (case-insensitive)
        company_lower = company.lower()
        for app in apps:
            if company_lower in app.company.lower():
                app.status = status
                if notes:
                    app.notes = notes
                self.save_all(apps)
                return app
        return None

    def get_all(self) -> list[JobApplication]:
        return self.load()

    def get_pending(self, min_days: int = 7) -> list[JobApplication]:
        """Candidatures en attente depuis plus de min_days jours."""
        return [a for a in self.load() if a.is_pending() and a.days_since_applied() >= min_days]

    def summary(self) -> str:
        apps = self.load()
        if not apps:
            return "Aucune candidature enregistrée."
        by_status: dict[str, list[str]] = {}
        for a in apps:
            by_status.setdefault(a.status, []).append(a.company)
        lines = [f"Total : {len(apps)} candidatures"]
        for status, companies in by_status.items():
            lines.append(f"  {status} : {', '.join(companies)}")
        return "\n".join(lines)
