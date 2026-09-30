"""
Multi-round ("dynamic") wrappers around single-round DA and TTC.

Each adapted round runs the mechanism over the students active in that window;
school capacity is the number of active students currently attending, adjusted
for arrivals and departures, so switches reallocate occupied seats.
"""

from .da import run_deferred_acceptance
from .ttc import run_top_trading_cycles
from .eadam import run_eadam


def run_dynamic(adapted_rounds: list, base_capacity: int,
                algorithm: str,
                extra_seats: dict | None = None) -> tuple[dict, dict, dict]:
    """
    Run dynamic DA (algorithm='DA'), TTC ('TTC'), or EADAM ('EADAM') across a
    sequence of adapted rounds for one (year, grade) market.

    `extra_seats` is an optional program -> seats mapping produced once for
    this market by `allocate_extra_seats`; when None, every touched school is
    simply seeded at `base_capacity`. See `_compute_capacities` below.

    Returns:
        placements    : student_id -> (school_id, round_index)
        all_cutoffs   : round_index -> (school_id -> worst priority admitted)
        per_round_stats: list of dicts with per-round diagnostics (unused here
                          but available for debugging)
    """
    if algorithm == "DA":
        run_single = run_deferred_acceptance
    elif algorithm == "TTC":
        run_single = run_top_trading_cycles
    elif algorithm == "EADAM":
        run_single = run_eadam
    else:
        raise ValueError(f"Unknown algorithm: {algorithm!r}")

    placements = {}                  # student_id -> (school_id, round_index)
    placed_students = []             # insertion order matters: see _compute_capacities
    unplaced_carry = []              # list of Student carried across rounds
    all_cutoffs = {}

    for r in adapted_rounds:
        active = list(r.students) + list(unplaced_carry)
        if not active:
            unplaced_carry = []
            continue

        capacities = _compute_capacities(active, placed_students, base_capacity,
                                          extra_seats)
        # Algorithms assume every student has ≥1 preference; bounce-back ensures it.
        single_round = run_single(active, capacities)

        unplaced_carry = []
        cutoffs = {}
        for student in active:
            placed_school = single_round.get(student.id)
            if placed_school is None or placed_school == student.current_school:
                unplaced_carry.append(student)
            else:
                placements[student.id] = (placed_school, r.index)
                placed_students.append((student, placed_school))

        for school_id in set(single_round.values()):
            admitted_ids = [sid for sid, sch in single_round.items()
                            if sch == school_id]
            if not admitted_ids:
                continue
            active_by_id = {s.id: s for s in active}
            cutoffs[school_id] = max(
                active_by_id[sid].priority_rank[school_id] for sid in admitted_ids
            )
        all_cutoffs[r.index] = cutoffs

    # Anyone still in unplaced_carry stays at current school.
    # Record them so stats see them.
    final_round_idx = adapted_rounds[-1].index if adapted_rounds else 0
    for student in unplaced_carry:
        placements[student.id] = (student.current_school, final_round_idx)

    return placements, all_cutoffs, {}


# -----------------------------------------------------------------------------
# Endogenous capacity: seats follow the students currently occupying them
# -----------------------------------------------------------------------------
def _compute_capacities(active_students: list,
                        placed_students: list,
                        base_capacity: int,
                        extra_seats: dict | None = None) -> dict:
    """
    capacity(s) = extra(s)
                + (# active with current_school == s)
                + (# already-placed students who LEFT s)
                - (# already-placed students who WERE placed at s)

    `extra(s)` is the number of additional (empty) seats given to school s:

      - extra_seats is None (the paper's baseline): extra(s) = base_capacity
        for every touched school, i.e. the same integer number of seats added
        everywhere regardless of how many students want a place there.

      - extra_seats is a dict: extra(s) = extra_seats.get(s, 0). The dict is
        built once per (year, grade) market by `allocate_extra_seats` below
        and is the same for every round and every algorithm, so DA, TTC and
        EADAM face identical capacities and the allocation does not vary
        across Monte Carlo draws.

    Every school that any active student might propose to (preferences or
    current_school), or that any placed student is associated with, is
    seeded at extra(s). Without this seeding, schools that no active
    student currently attends and that have not yet seen any placement are
    absent from the returned dict, so da.py's `capacities.get(school_id, 0)`
    treats them as having capacity 0 regardless of base_capacity. That bug
    locked an entire class of "target-only" schools out of the matching.
    """
    touched_schools: set = set()
    for st in active_students:
        touched_schools.update(st.complete_preferences)
        if st.current_school is not None:
            touched_schools.add(st.current_school)
    for st, placed_school in placed_students:
        if st.current_school is not None:
            touched_schools.add(st.current_school)
        touched_schools.add(placed_school)

    cap: dict = {}
    for s in touched_schools:
        cap.setdefault(s, base_capacity if extra_seats is None
                          else extra_seats.get(s, 0))

    for st in active_students:
        if st.current_school is not None:
            cap[st.current_school] += 1
    for st, placed_school in placed_students:
        if st.current_school is not None:
            cap[st.current_school] += 1
        cap[placed_school] -= 1
    return cap


# -----------------------------------------------------------------------------
# Market-level seat budget
# -----------------------------------------------------------------------------
def allocate_extra_seats(market_students: list,
                         overcapacity_pct: float,
                         demand_proportional: bool) -> dict:
    """
    Distribute a market-level budget of additional (empty) seats across the
    programs of one (year, grade) market.

    The budget is defined exactly as the paper defines the x-axis of the
    capacity figure -- additional seats as a percentage of active students:

        budget = round(overcapacity_pct / 100 * len(market_students))

    and is allocated across P, the set of programs that appear in at least one
    student's rank-ordered list in this market. P deliberately matches the
    `n_unique_programs` column of diagnostic_unique_programs.csv, so the seat
    budget and that diagnostic are computed over the same set of programs.

      - demand_proportional=False: the budget is split as evenly as possible
        across P.
      - demand_proportional=True:  the budget is split in proportion to
        demand(p) = the number of students in the market who rank p anywhere
        in their list. Programs nobody ranks get nothing; oversubscribed
        programs get more than an even share.

    Both branches use largest-remainder (Hamilton) rounding, so the seats
    handed out sum to `budget` exactly and the two allocation modes are
    directly comparable at any given overcapacity_pct.

    Reads `preferences` (the submitted ROL), never `complete_preferences`
    (which has the bounce-back current school appended), so a student is
    never counted as demanding the school they already attend. Because the
    two lists are separate attributes this holds regardless of call order.
    """
    if not market_students or overcapacity_pct <= 0:
        return {}

    programs = sorted({p for st in market_students for p in st.preferences})
    if not programs:
        return {}

    budget = int(round(overcapacity_pct / 100.0 * len(market_students)))
    if budget <= 0:
        return {}

    if demand_proportional:
        demand = {p: 0 for p in programs}
        for st in market_students:
            for p in st.preferences:
                demand[p] += 1
        total = sum(demand.values())
        weights = ({p: demand[p] / total for p in programs} if total > 0
                   else {p: 1.0 / len(programs) for p in programs})
    else:
        weights = {p: 1.0 / len(programs) for p in programs}

    quota = {p: budget * weights[p] for p in programs}
    seats = {p: int(quota[p]) for p in programs}
    # Largest remainder: hand the leftover seats to the largest fractional
    # parts, breaking ties on program id so the result is deterministic.
    leftover = budget - sum(seats.values())
    if leftover > 0:
        order = sorted(programs,
                       key=lambda p: (-(quota[p] - seats[p]), p))
        for p in order[:leftover]:
            seats[p] += 1
    return seats
