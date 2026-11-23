"""Canonical profile departments and conservative, idempotent legacy conversion."""

from fastapi import HTTPException
from sqlalchemy import select

from backend.database import User


DEPARTMENTS = (
    ("EECS", "Electrical Engineering & Computer Science (College)"),
    ("CS", "Computer Science"),
    ("EE", "Electrical Engineering"),
    ("IBP", "International Bachelor Degree Program"),
    ("IPEECS", "Interdisciplinary Program of EECS"),
    ("IMBA", "International Master of Business Administration"),
    ("MBA", "Master of Business Administration"),
    ("EMBA", "Executive Master of Business Administration"),
    ("PME", "Power Mechanical Engineering"),
    ("MSE", "Materials Science & Engineering"),
    ("CHE", "Chemical Engineering"),
    ("IEEM", "Industrial Engineering & Engineering Management"),
    ("ESS", "Engineering & System Science"),
    ("BMES", "Biomedical Engineering & Environmental Sciences"),
    ("MATH", "Mathematics"),
    ("PHYS", "Physics"),
    ("CHEM", "Chemistry"),
    ("STAT", "Statistics & Data Science"),
    ("LS", "Life Science"),
    ("MS", "Medical Science"),
    ("ECON", "Economics"),
    ("QF", "Quantitative Finance"),
    ("TM", "Technology Management"),
    ("FLL", "Foreign Languages & Literature"),
    ("CL", "Chinese Literature"),
    ("HSS", "Humanities & Social Sciences"),
    ("ECE", "Early Childhood Education"),
    ("EDU", "Education"),
    ("AD", "Art & Design"),
    ("MUSIC", "Music"),
)
DEPARTMENT_CODES = frozenset(code for code, _ in DEPARTMENTS)


def department_options():
    return [{"value": code, "label": f"{code} — {name}"} for code, name in DEPARTMENTS]


def validate_department(value):
    """New writes accept only canonical codes or an optional empty selection."""
    value = value.strip() if value else None
    if value and value not in DEPARTMENT_CODES:
        raise HTTPException(422, "Choose a department from the list or leave it empty.")
    return value or None


def _key(value):
    return " ".join(value.casefold().split())


# Exact names, labels, or codes after case/whitespace normalization only.
# Never guess from substrings or fuzzy spelling: CHE and CHEM are distinct.
LEGACY_CODES = {_key(alias): code for code, name in DEPARTMENTS
                for alias in (code, name, f"{code} — {name}")}


def normalize_existing_departments(session_factory):
    """One transaction; unknown text stays intact; safe on every startup.

    No schema changes, record deletion, or updates to credentials/workout data.
    Exceptions roll back all conversions and prevent startup with partial changes.
    """
    changed = 0
    with session_factory.begin() as db:
        for user in db.scalars(select(User).where(User.department.is_not(None))):
            original = user.department
            normalized = LEGACY_CODES.get(_key(original), original) if original.strip() else None
            if normalized != original:
                user.department = normalized
                changed += 1
    return changed
