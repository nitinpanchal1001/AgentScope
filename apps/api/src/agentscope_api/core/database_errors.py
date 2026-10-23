from sqlalchemy.exc import IntegrityError


def is_unique_violation(error: IntegrityError) -> bool:
    """Return true only for database uniqueness violations.

    PostgreSQL drivers expose SQLSTATE 23505. SQLite is used by the fast API
    test suite and reports uniqueness through its error message instead.
    """

    current: BaseException | None = error.orig
    while current is not None:
        if getattr(current, "sqlstate", None) == "23505":
            return True
        current = current.__cause__
    return "unique constraint failed" in str(error.orig).lower()
