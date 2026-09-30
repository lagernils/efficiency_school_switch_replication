"""
Small dataclasses used across the simulation.

Design note: priorities and preferences are stored on the Student so that a
single object tells you everything an algorithm needs.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class Student:
    id: str                           # ParticipantId (unique per (student, raw round))
    grade: int
    year: int                         # academic year (June 30 t .. June 29 t+1)
    current_school: Optional[str]     # spgid, or None (dropped before use)
    preferences: list                 # the submitted ROL: ordered spgid, never mutated
    lottery_number: int               # drawn uniformly from [1, LOTTERY_MAX]
    application_date: date            # randomised or raw, used for round assignment
    studentid: str = ""               # underlying studentId (same student across raw rounds)
    # Filled in by preprocessing.append_bounce_back: the ROL with the current
    # school appended if unranked. This is what the algorithms propose over;
    # `preferences` stays the submitted list so demand-side code (e.g.
    # dynamic.allocate_extra_seats) can read it without ordering constraints.
    complete_preferences: list = field(default_factory=list)
    # Filled in by priorities.assign_priority_ranks:
    priority_rank: dict = field(default_factory=dict)   # spgid -> int rank
    # EADAM-specific state.
    # `consent` == 1 means the student consents to waive priority in EADAM;
    # when `full_consent_bool` is False at load time, all students get consent=0
    # and EADAM's output equals student-proposing DA.
    consent: int = 1
    # Working preference list EADAM prunes as it removes consenting interrupting
    # pairs; kept separate from `preferences` so the originals survive for
    # downstream welfare analysis.
    eadam_preferences: list = field(default_factory=list)


@dataclass
class School:
    id: str                  # spgid
    grade: int
    year: int
    name: str = ""


@dataclass
class AdaptedRound:
    index: int               # 1-based position within the year-grade sequence
    year: int
    grade: int
    start_date: date
    end_date: date           # inclusive
    # Populated during assignment:
    students: list = field(default_factory=list)   # Students whose randomised date falls in window


@dataclass
class RoundOutcome:
    """Result of running DA or TTC once on a single adapted round."""
    placements: dict                 # student_id -> spgid (placement)
    cutoffs: dict                    # spgid -> worst priority rank admitted (or None)
