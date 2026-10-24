"""Create a staff login:  python -m app.create_user doctor@example.com 'a-strong-password'"""
import sys

from sqlalchemy import select

from .db import Base, SessionLocal, engine
from .models import User
from .security import hash_password


def main():
    if len(sys.argv) != 3 or len(sys.argv[2]) < 8:
        sys.exit("usage: python -m app.create_user <email> <password (8+ chars)>")
    Base.metadata.create_all(bind=engine)
    email = sys.argv[1].lower()
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            sys.exit("A user with that email already exists")
        db.add(User(email=email, password_hash=hash_password(sys.argv[2])))
        db.commit()
    print(f"Created user {email}")


if __name__ == "__main__":
    main()
