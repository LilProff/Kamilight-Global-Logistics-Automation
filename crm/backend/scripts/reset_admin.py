"""Recovery tool: set a new password for an account, or create an administrator, straight in the database.

Use it only if every administrator is locked out. Run it where DATABASE_URL points at the real database
(for example Render > the service > Shell):

    python -m scripts.reset_admin someone@kamilightglobal.com

It asks for the new password (nothing is echoed or logged), applies the usual password rules, signs the
account out everywhere, clears any lockout, and makes sure the account is an active administrator.
"""

import getpass
import sys

from sqlalchemy import delete, select

from app.db import Base, SessionLocal, engine
from app.models import LoginAttempt, User
from app.security import hash_password, password_problem


def main() -> int:
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        print("Usage: python -m scripts.reset_admin someone@example.com")
        return 2
    email = sys.argv[1].strip().lower()
    password = getpass.getpass("New password: ")
    if password != getpass.getpass("Again: "):
        print("The two passwords don't match.")
        return 1
    problem = password_problem(password, email)
    if problem:
        print(problem)
        return 1
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, name="Administrator", password_hash=hash_password(password), role="admin")
            db.add(user)
            action = "Created administrator"
        else:
            user.password_hash, user.role, user.active = hash_password(password), "admin", True
            user.token_version += 1
            action = "Reset password for"
        db.execute(delete(LoginAttempt).where(LoginAttempt.email == email))
        db.commit()
    print(f"{action} {email}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
