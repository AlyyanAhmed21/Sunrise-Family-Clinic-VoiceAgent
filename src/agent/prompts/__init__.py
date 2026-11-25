"""Versioned system prompts. Each prompt is a Markdown file rendered with today's date."""

from __future__ import annotations

from datetime import datetime
from importlib.resources import files
from string import Template
from typing import Literal

from agent.spoken import CLINIC_TZ, upcoming_calendar

PromptName = Literal["receptionist", "after_hours"]


def render_prompt(name: PromptName, now: datetime) -> str:
    local = now.astimezone(CLINIC_TZ)
    template = Template(files(__package__).joinpath(f"{name}.md").read_text(encoding="utf-8"))
    return template.substitute(
        today_line=f"Right now it is {local:%A, %B} {local.day}, {local.year}, "
        f"{local:%I:%M %p} Eastern Time.",
        calendar=upcoming_calendar(local.date()),
    )
