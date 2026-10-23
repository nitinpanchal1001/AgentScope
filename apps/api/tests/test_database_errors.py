import sqlite3

from sqlalchemy.exc import IntegrityError

from agentscope_api.core.database_errors import is_unique_violation


def test_only_unique_integrity_errors_are_classified_as_conflicts() -> None:
    unique = IntegrityError(
        "insert",
        {},
        sqlite3.IntegrityError("UNIQUE constraint failed: organizations.slug"),
    )
    foreign_key = IntegrityError(
        "insert",
        {},
        sqlite3.IntegrityError("FOREIGN KEY constraint failed"),
    )

    assert is_unique_violation(unique)
    assert not is_unique_violation(foreign_key)
