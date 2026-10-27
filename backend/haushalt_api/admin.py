"""Way back in when no admin can log in any more. Runs in the API container:

    podman compose -f deployment/compose.yaml exec api python -m haushalt_api.admin reset-password <username>
    podman compose -f deployment/compose.yaml exec api python -m haushalt_api.admin make-admin <username>
    podman compose -f deployment/compose.yaml exec api python -m haushalt_api.admin list

Whoever can run commands in the container owns the data anyway, so this
needs no further login.
"""

import argparse
import sys

from sqlalchemy import select

from .auth import hash_password
from . import tenancy
from .db import SessionLocal, User, init_db
from .passwords import one_time_password


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m haushalt_api.admin")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (
        ("reset-password", "print a one-time password, end all sessions, enable the account"),
        ("make-admin", "give the account the admin role and enable it"),
    ):
        commands.add_parser(name, help=text).add_argument("username")
    commands.add_parser("list", help="list the accounts")
    args = parser.parse_args(argv)

    init_db()
    # the operator's tool: accounts of every household
    with tenancy.unscoped(SessionLocal()) as session:
        if args.command == "list":
            for user in session.scalars(select(User).order_by(User.username)):
                flags = [f for f, on in (("admin", user.is_admin), ("disabled", user.disabled)) if on]
                print(user.username, *flags)
            return 0
        user = session.scalar(select(User).where(User.username == args.username))
        if user is None:
            print(f"no account {args.username!r}", file=sys.stderr)
            return 1
        user.disabled = False
        user.token_version += 1
        if args.command == "make-admin":
            user.is_admin = True
            session.commit()
            print(f"{user.username} is admin now")
        else:
            password = one_time_password()
            user.password_hash = hash_password(password)
            user.must_change_password = True
            session.commit()
            print(f"one-time password for {user.username}: {password}")
            print("It must be replaced at the next login.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
