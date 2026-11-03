"""
finpilot/seed.py
Realistic 6-month Indian personal finance demo dataset generator (salary, freelance,
rent, groceries, fuel, subscriptions, shopping, dining, bills, health).
"""

from __future__ import annotations

import calendar
from datetime import date

from models import Budget, Transaction, TransactionType


def _subtract_months(ref: date, months_back: int) -> tuple[int, int]:
    """Return (year, month) `months_back` prior to `ref`."""
    total_months = ref.year * 12 + (ref.month - 1) - months_back
    return total_months // 12, (total_months % 12) + 1


def generate_demo_data(
    reference_date: date | None = None,
) -> tuple[list[Transaction], list[Budget]]:
    """
    Generate 6 months of deterministic, realistic Indian fintech transactions
    and category budgets so FinPilot looks impressive immediately on first launch.
    All amounts are stored in exact integer paise (₹1 = 100 paise).
    """
    today = reference_date or date.today()
    transactions: list[Transaction] = []

    monthly_templates = [
        # (months_back, freelance_rupees, shopping_rupees, dining_rupees, travel_rupees, health_rupees)
        (5, 18000, 6400, 7200, 4200, 1500),
        (4, 24000, 9200, 6800, 5100, 800),
        (3, 15000, 5800, 7900, 8400, 2200),
        (2, 32000, 14500, 8400, 6200, 1200),
        (1, 22000, 8900, 9100, 4800, 1900),
        (0, 28500, 11800, 10400, 5600, 2400),
    ]

    for m_back, freelance, shopping, dining, travel, health in monthly_templates:
        yr, mo = _subtract_months(today, m_back)
        max_day = calendar.monthrange(yr, mo)[1]
        if m_back == 0:
            max_day = min(max_day, today.day)

        def d_str(preferred_day: int) -> str:
            clamped = max(1, min(preferred_day, max_day))
            return f"{yr:04d}-{mo:02d}-{clamped:02d}"

        # 1. Primary Salary Income (₹1,15,000/month)
        transactions.append(
            Transaction(
                type=TransactionType.INCOME,
                amount_paise=115000 * 100,
                category="Salary",
                date=d_str(1),
                note="Monthly Tech Corp Salary Credit (NEFT)",
            )
        )

        # 2. Freelance / Consulting Income
        transactions.append(
            Transaction(
                type=TransactionType.INCOME,
                amount_paise=freelance * 100,
                category="Freelance",
                date=d_str(14),
                note="UI/UX & Python Sprint Retainer",
            )
        )

        # 3. Apartment Rent (₹28,000)
        transactions.append(
            Transaction(
                type=TransactionType.EXPENSE,
                amount_paise=28000 * 100,
                category="Rent",
                date=d_str(3),
                note="2BHK Apartment Rent via UPI",
            )
        )

        # 4. Groceries (2 batches)
        transactions.append(
            Transaction(
                type=TransactionType.EXPENSE,
                amount_paise=4250 * 100,
                category="Groceries",
                date=d_str(5),
                note="BigBasket Monthly Staples & Produce",
            )
        )
        transactions.append(
            Transaction(
                type=TransactionType.EXPENSE,
                amount_paise=3180 * 100,
                category="Groceries",
                date=d_str(18),
                note="FreshMart Organic Dairy & Vegetables",
            )
        )

        # 5. Dining / Food Delivery
        transactions.append(
            Transaction(
                type=TransactionType.EXPENSE,
                amount_paise=(dining // 2) * 100,
                category="Food",
                date=d_str(8),
                note="Zomato Weekend Dinner & Artisanal Coffee",
            )
        )
        transactions.append(
            Transaction(
                type=TransactionType.EXPENSE,
                amount_paise=(dining - dining // 2) * 100,
                category="Food",
                date=d_str(21),
                note="Swiggy Team Lunch & Specialty Bakery",
            )
        )

        # 6. Utilities & Broadband Bills
        transactions.append(
            Transaction(
                type=TransactionType.EXPENSE,
                amount_paise=3850 * 100,
                category="Bills",
                date=d_str(7),
                note="BESCOM Electricity & Airtel Fiber 300Mbps",
            )
        )

        # 7. Fuel & Metro Commute
        transactions.append(
            Transaction(
                type=TransactionType.EXPENSE,
                amount_paise=3400 * 100,
                category="Fuel",
                date=d_str(11),
                note="IndianOil XP95 Fuel Refill",
            )
        )

        # 8. Travel
        transactions.append(
            Transaction(
                type=TransactionType.EXPENSE,
                amount_paise=travel * 100,
                category="Travel",
                date=d_str(16),
                note="Airport Cab & Intercity Express Booking",
            )
        )

        # 9. Subscriptions & Entertainment
        transactions.append(
            Transaction(
                type=TransactionType.EXPENSE,
                amount_paise=1499 * 100,
                category="Subscriptions",
                date=d_str(12),
                note="Netflix 4K, Spotify Duo & iCloud+ 200GB",
            )
        )
        transactions.append(
            Transaction(
                type=TransactionType.EXPENSE,
                amount_paise=1850 * 100,
                category="Entertainment",
                date=d_str(23),
                note="IMAX Tickets & Live Indie Concert",
            )
        )

        # 10. Shopping
        transactions.append(
            Transaction(
                type=TransactionType.EXPENSE,
                amount_paise=shopping * 100,
                category="Shopping",
                date=d_str(19),
                note="Amazon Electronics & Running Gear",
            )
        )

        # 11. Health & Fitness
        transactions.append(
            Transaction(
                type=TransactionType.EXPENSE,
                amount_paise=health * 100,
                category="Health",
                date=d_str(25),
                note="Cult.fit Pass & Pharmacy Essentials",
            )
        )

    budgets: list[Budget] = [
        Budget(category="Food", monthly_limit_paise=12000 * 100),
        Budget(category="Groceries", monthly_limit_paise=9000 * 100),
        Budget(category="Rent", monthly_limit_paise=30000 * 100),
        Budget(category="Shopping", monthly_limit_paise=12000 * 100),
        Budget(category="Travel", monthly_limit_paise=7500 * 100),
        Budget(category="Bills", monthly_limit_paise=5000 * 100),
        Budget(category="Fuel", monthly_limit_paise=4500 * 100),
        Budget(category="Entertainment", monthly_limit_paise=3500 * 100),
        Budget(category="Subscriptions", monthly_limit_paise=2000 * 100),
        Budget(category="Health", monthly_limit_paise=3500 * 100),
    ]

    return transactions, budgets
