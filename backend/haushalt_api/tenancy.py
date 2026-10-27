"""One household per session: every query of household data (HouseholdOwned
rows and users) gets "household_id = the session's household", every new
row gets that household. Without a bound household nothing of any
household is visible, so a forgotten bind shows nothing instead of all.

Only the login, the CLI, the migrations and jobs across all households
(receipt file expiry, meter polling) read beyond one household, and they
say so with everywhere() or unscoped().
"""

from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from .db import HouseholdOwned, User

HOUSEHOLD = "household_id"
ALL = "all_households"
_NOBODY = -1


def bind(session: Session, household_id: int | None) -> None:
    session.info[HOUSEHOLD] = household_id


def current(session: Session) -> int | None:
    return session.info.get(HOUSEHOLD)


def unscoped(session: Session) -> Session:
    """The whole session sees every household (CLI, migrations)."""
    session.info[ALL] = True
    return session


EVERYWHERE = {ALL: True}


def everywhere(statement):
    """One statement that reads every household."""
    return statement.execution_options(**EVERYWHERE)


@event.listens_for(Session, "do_orm_execute")
def _only_own_household(state) -> None:
    if not (state.is_select or state.is_update or state.is_delete):
        return
    if state.session.info.get(ALL) or state.execution_options.get(ALL):
        return
    household = state.session.info.get(HOUSEHOLD)
    household = _NOBODY if household is None else household
    state.statement = state.statement.options(
        with_loader_criteria(HouseholdOwned, lambda cls: cls.household_id == household, include_aliases=True),
        with_loader_criteria(User, lambda cls: cls.household_id == household, include_aliases=True),
    )


@event.listens_for(Session, "before_flush")
def _new_rows_get_the_household(session: Session, _context, _instances) -> None:
    household = session.info.get(HOUSEHOLD)
    for row in session.new:
        if isinstance(row, User) and row.household_id is None and not row.is_operator:
            row.household_id = household  # a member of the bound household
        elif isinstance(row, HouseholdOwned) and row.household_id is None:
            if household is None:
                raise RuntimeError(f"{type(row).__name__} without a household")
            row.household_id = household
