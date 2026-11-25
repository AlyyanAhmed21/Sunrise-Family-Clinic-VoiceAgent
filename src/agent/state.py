from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from pydantic import SecretStr

from clinic.clock import Clock
from clinic.models import AvailableSlot, CallMode
from clinic.security.parsing import DateParts
from clinic.service import ClinicService


@dataclass(slots=True)
class CallState:
    """Server-side state for one call (LiveKit `userdata`).

    Identity values captured from speech live here and are never shown to the LLM.
    """

    call_id: str
    mode: CallMode
    service: ClinicService
    clock: Clock
    verified: bool = False
    dob: DateParts = field(default_factory=DateParts)
    last_four: SecretStr | None = field(default=None, repr=False)
    caller_confirmed: bool = False
    pending_action: str | None = field(default=None, repr=False)
    offered_slots: dict[str, AvailableSlot] = field(default_factory=dict)

    @property
    def today(self) -> date:
        return self.clock.now().date()

    def captured_dob(self) -> date | None:
        return self.dob.to_date(today=self.today)

    def clear_identity(self) -> None:
        self.dob = DateParts()
        self.last_four = None

    def await_confirmation(self, action: str) -> None:
        """Remember what was read back; only the caller's next "yes" can approve it."""
        self.pending_action = action
        self.caller_confirmed = False

    def take_confirmation(self, action: str) -> bool:
        approved = self.pending_action == action and self.caller_confirmed
        if approved:
            self.pending_action = None
            self.caller_confirmed = False
        return approved
