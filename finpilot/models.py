"""
finpilot/models.py
Data models, enumerations, and Indian currency formatting helpers for FinPilot.
Uses integer paise (1 INR = 100 paise) internally to eliminate floating-point money bugs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from typing import Any


class TransactionType(str, Enum):
    """Represents whether a transaction adds or subtracts funds."""

    INCOME = "INCOME"
    EXPENSE = "EXPENSE"


INCOME_CATEGORIES: tuple[str, ...] = (
    "Salary",
    "Freelance",
    "Investments",
    "Dividends",
    "Refunds",
    "Gifts",
    "Other",
)

EXPENSE_CATEGORIES: tuple[str, ...] = (
    "Food",
    "Rent",
    "Travel",
    "Shopping",
    "Bills",
    "Subscriptions",
    "Entertainment",
    "Health",
    "Fuel",
    "Groceries",
    "Other",
)

# Clean single-codepoint icons (no \ufe0f variation selectors that cause wide gaps on Windows Tk 8.6)
CATEGORY_ICONS: dict[str, str] = {
    "Salary": "💼",
    "Freelance": "💻",
    "Investments": "📈",
    "Dividends": "🏦",
    "Refunds": "↩",
    "Gifts": "🎁",
    "Food": "🍴",
    "Groceries": "🛒",
    "Rent": "🏠",
    "Travel": "✈",
    "Fuel": "⛽",
    "Shopping": "🛍",
    "Bills": "⚡",
    "Subscriptions": "🔄",
    "Entertainment": "🎬",
    "Health": "✚",
    "Other": "📌",
}


def rupees_to_paise(value: str | int | float | Decimal) -> int:
    """
    Convert a user-supplied rupee value (e.g. '1250.50') to integer paise (125050).
    Raises ValueError if the input is invalid, negative, zero, or has > 2 decimal places.
    """
    raw = str(value).strip().replace(",", "")
    if not raw:
        raise ValueError("Amount is required.")
    try:
        dec = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("Enter a valid numeric amount.") from exc

    if dec <= Decimal("0"):
        raise ValueError("Amount must be greater than zero.")

    if dec > Decimal("999999999.99"):
        raise ValueError("Amount exceeds maximum limit (₹99,99,99,999.99).")

    exponent = dec.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise ValueError("Amount can have at most 2 decimal places.")

    paise = int((dec * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return paise


def paise_to_rupees_decimal(paise: int) -> Decimal:
    """Convert integer paise back to a 2-decimal-place Decimal."""
    return (Decimal(paise) / Decimal("100")).quantize(Decimal("0.01"))


def format_indian_currency(
    paise: int,
    symbol: str = "₹",
    show_decimals: bool = False,
    signed: bool = False,
) -> str:
    """
    Format integer paise using Indian numbering system (e.g., ₹1,25,000 or ₹12,450.50).
    First group of 3 digits from right, then groups of 2 digits (lakhs, crores).
    """
    is_negative = paise < 0
    abs_paise = abs(int(paise))
    rupees = abs_paise // 100
    rem_paise = abs_paise % 100

    s = str(rupees)
    if len(s) > 3:
        last_three = s[-3:]
        rest = s[:-3]
        groups: list[str] = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        formatted_int = ",".join(groups) + "," + last_three
    else:
        formatted_int = s

    if show_decimals or rem_paise > 0:
        number_part = f"{formatted_int}.{rem_paise:02d}"
    else:
        number_part = formatted_int

    prefix = ""
    if is_negative:
        prefix = "-"
    elif signed and paise > 0:
        prefix = "+"

    return f"{prefix}{symbol}{number_part}"


def validate_iso_date(date_str: str) -> str:
    """
    Validate a YYYY-MM-DD date string and ensure it is not in the future.
    Returns normalized YYYY-MM-DD string or raises ValueError.
    """
    cleaned = date_str.strip()
    if not cleaned:
        raise ValueError("Date is required (YYYY-MM-DD).")
    try:
        parsed = datetime.strptime(cleaned, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Date must be in YYYY-MM-DD format.") from exc

    if parsed > date.today():
        raise ValueError("Future dates beyond today are not allowed.")

    return parsed.strftime("%Y-%m-%d")


@dataclass(slots=True)
class Transaction:
    """
    Immutable-style financial transaction record.
    `amount_paise` stores exact integer paise (₹1.00 = 100 paise) to avoid float errors.
    """

    type: TransactionType
    amount_paise: int
    category: str
    date: str  # YYYY-MM-DD
    note: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def amount_rupees(self) -> float:
        """Return amount in rupees as float strictly for chart plotting."""
        return self.amount_paise / 100.0

    @property
    def month_key(self) -> str:
        """Return YYYY-MM key for fast monthly grouping."""
        return self.date[:7]

    def to_dict(self) -> dict[str, Any]:
        """Serialize Transaction to a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "amount_paise": self.amount_paise,
            "category": self.category,
            "note": self.note,
            "date": self.date,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Transaction:
        """Deserialize Transaction from a dictionary with safe validation."""
        tx_type = TransactionType(str(data["type"]).upper())
        amount_paise = int(data["amount_paise"])
        if amount_paise <= 0:
            raise ValueError("Transaction amount_paise must be positive.")
        return cls(
            id=str(data.get("id") or uuid.uuid4()),
            type=tx_type,
            amount_paise=amount_paise,
            category=str(data["category"]).strip() or "Other",
            note=str(data.get("note", "")).strip(),
            date=str(data["date"]).strip(),
        )


@dataclass(slots=True)
class Budget:
    """
    Monthly spending limit for a specific expense category.
    `monthly_limit_paise` stores exact integer paise.
    """

    category: str
    monthly_limit_paise: int

    @property
    def monthly_limit_rupees(self) -> float:
        """Return monthly limit in rupees for display/charts."""
        return self.monthly_limit_paise / 100.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize Budget to a JSON-compatible dictionary."""
        return {
            "category": self.category,
            "monthly_limit_paise": self.monthly_limit_paise,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Budget:
        """Deserialize Budget from a dictionary."""
        limit = int(data["monthly_limit_paise"])
        if limit < 0:
            raise ValueError("Budget limit cannot be negative.")
        return cls(
            category=str(data["category"]).strip(),
            monthly_limit_paise=limit,
        )
