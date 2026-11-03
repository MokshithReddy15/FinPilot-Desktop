"""
finpilot/store.py
Zero-UI DataStore with CRUD operations, cached aggregations, observer pattern,
background thread JSON/CSV persistence, and budget threshold alerts.
"""

from __future__ import annotations

import calendar
import csv
import json
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

from models import (
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
    Budget,
    Transaction,
    TransactionType,
    format_indian_currency,
)

StoreListener = Callable[[str, dict[str, Any]], None]


@dataclass(slots=True)
class BudgetStatus:
    """Computed status for a single category budget in a given month."""

    category: str
    limit_paise: int
    spent_paise: int
    remaining_paise: int
    percent_used: float
    level: str  # "ok" (<70%), "warning" (70-99%), "danger" (100%+)


@dataclass(slots=True)
class MonthlyComparison:
    """Comparison between selected month and previous month."""

    current_month: str
    previous_month: str
    current_income_paise: int
    previous_income_paise: int
    current_expense_paise: int
    previous_expense_paise: int
    expense_change_pct: float | None  # None when previous month had 0 expense


class DataStore:
    """
    Central state store for FinPilot.
    Strictly decoupled from Tkinter/UI imports.
    Caches all monthly and category aggregations and invalidates only on mutation.
    """

    def __init__(
        self,
        storage_path: str | Path = "finpilot_data.json",
        currency_symbol: str = "₹",
    ) -> None:
        self.storage_path = Path(storage_path)
        self.currency_symbol = currency_symbol
        self._transactions: list[Transaction] = []
        self._tx_by_id: dict[str, Transaction] = {}
        self._budgets: dict[str, Budget] = {}
        self._custom_categories: list[str] = []
        self._listeners: list[StoreListener] = []
        self._io_lock = threading.Lock()

        # Cached aggregations (Rule 6: Cache aggregations and invalidate only on change)
        self._cache_valid: bool = False
        self._total_income_paise: int = 0
        self._total_expense_paise: int = 0
        self._monthly_income: dict[str, int] = {}
        self._monthly_expense: dict[str, int] = {}
        self._monthly_category_expense: dict[str, dict[str, int]] = {}
        self._monthly_daily_expense: dict[str, dict[int, int]] = {}
        self._available_months: list[str] = []

    # -------------------- Observer System --------------------

    def subscribe(self, callback: StoreListener) -> Callable[[], None]:
        """Register a listener callback(event_type, payload). Returns unsubscribe fn."""
        if callback not in self._listeners:
            self._listeners.append(callback)

        def unsubscribe() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return unsubscribe

    def _notify(self, event: str, payload: dict[str, Any] | None = None) -> None:
        """Notify all registered observers of a state change."""
        info = payload or {}
        for listener in list(self._listeners):
            listener(event, info)

    # -------------------- Cache Management (Section 5 Rule 6) --------------------

    def _invalidate_cache(self) -> None:
        """Mark cached aggregations dirty after any mutation."""
        self._cache_valid = False

    def _ensure_cache(self) -> None:
        """Recompute aggregations in a single O(N) pass only when cache is invalid."""
        if self._cache_valid:
            return

        total_inc = 0
        total_exp = 0
        m_inc: dict[str, int] = defaultdict(int)
        m_exp: dict[str, int] = defaultdict(int)
        m_cat_exp: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        m_day_exp: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        months_set: set[str] = {date.today().strftime("%Y-%m")}

        # Keep transactions sorted newest-first by date
        self._transactions.sort(key=lambda t: (t.date, t.id), reverse=True)

        for tx in self._transactions:
            m_key = tx.month_key
            months_set.add(m_key)
            if tx.type == TransactionType.INCOME:
                total_inc += tx.amount_paise
                m_inc[m_key] += tx.amount_paise
            else:
                total_exp += tx.amount_paise
                m_exp[m_key] += tx.amount_paise
                m_cat_exp[m_key][tx.category] += tx.amount_paise
                try:
                    day_num = int(tx.date[8:10])
                    m_day_exp[m_key][day_num] += tx.amount_paise
                except ValueError:
                    pass

        self._total_income_paise = total_inc
        self._total_expense_paise = total_exp
        self._monthly_income = dict(m_inc)
        self._monthly_expense = dict(m_exp)
        self._monthly_category_expense = {k: dict(v) for k, v in m_cat_exp.items()}
        self._monthly_daily_expense = {k: dict(v) for k, v in m_day_exp.items()}
        self._available_months = sorted(months_set, reverse=True)
        self._cache_valid = True

    # -------------------- Category Helpers --------------------

    def get_categories(self, tx_type: TransactionType) -> list[str]:
        """Return available categories for INCOME or EXPENSE, including custom ones."""
        base = list(
            INCOME_CATEGORIES
            if tx_type == TransactionType.INCOME
            else EXPENSE_CATEGORIES
        )
        for custom in self._custom_categories:
            if custom not in base:
                base.insert(-1, custom)
        return base

    def add_custom_category(self, category: str) -> None:
        """Register a custom category name."""
        cleaned = category.strip()
        if not cleaned:
            raise ValueError("Category name cannot be empty.")
        if (
            cleaned not in self._custom_categories
            and cleaned not in EXPENSE_CATEGORIES
            and cleaned not in INCOME_CATEGORIES
        ):
            self._custom_categories.append(cleaned)
            self._notify("category_added", {"category": cleaned})

    # -------------------- Transaction CRUD --------------------

    def get_transactions(
        self,
        search: str = "",
        tx_type: str = "ALL",
        category: str = "ALL",
        month: str = "ALL",
        sort_by: str = "date",
        descending: bool = True,
    ) -> list[Transaction]:
        """
        Return filtered and sorted transactions.
        Fast in-memory filtering designed to handle 5,000+ records in < 5ms.
        """
        self._ensure_cache()
        query = search.strip().lower()

        result: list[Transaction] = []
        for tx in self._transactions:
            if tx_type != "ALL" and tx.type.value != tx_type:
                continue
            if category != "ALL" and tx.category != category:
                continue
            if month != "ALL" and tx.month_key != month:
                continue
            if query:
                haystack = f"{tx.category} {tx.note} {tx.date} {tx.amount_paise / 100:.2f}".lower()
                if query not in haystack:
                    continue
            result.append(tx)

        if sort_by == "amount":
            result.sort(key=lambda t: t.amount_paise, reverse=descending)
        elif sort_by == "category":
            result.sort(key=lambda t: t.category.lower(), reverse=descending)
        elif sort_by == "type":
            result.sort(key=lambda t: t.type.value, reverse=descending)
        else:
            result.sort(key=lambda t: (t.date, t.id), reverse=descending)

        return result

    def add_transaction(self, tx: Transaction) -> dict[str, Any]:
        """
        Add a transaction, update caches, and check if any budget threshold (80% or 100%)
        was crossed by this new expense.
        """
        self._ensure_cache()
        prev_spent = 0
        limit_paise = 0
        if tx.type == TransactionType.EXPENSE and tx.category in self._budgets:
            prev_spent = self._monthly_category_expense.get(tx.month_key, {}).get(
                tx.category, 0
            )
            limit_paise = self._budgets[tx.category].monthly_limit_paise

        self._transactions.append(tx)
        self._tx_by_id[tx.id] = tx
        self._invalidate_cache()
        self._ensure_cache()

        budget_alert: dict[str, Any] | None = None
        if tx.type == TransactionType.EXPENSE and limit_paise > 0:
            new_spent = self._monthly_category_expense.get(tx.month_key, {}).get(
                tx.category, 0
            )
            prev_pct = (prev_spent / limit_paise) * 100.0
            new_pct = (new_spent / limit_paise) * 100.0
            if prev_pct < 100.0 <= new_pct:
                budget_alert = {
                    "level": "danger",
                    "category": tx.category,
                    "percent": round(new_pct, 1),
                    "message": (
                        f"Budget exceeded for {tx.category}! "
                        f"Spent {format_indian_currency(new_spent, self.currency_symbol)} "
                        f"of {format_indian_currency(limit_paise, self.currency_symbol)} ({new_pct:.0f}%)."
                    ),
                }
            elif prev_pct < 80.0 <= new_pct:
                budget_alert = {
                    "level": "warning",
                    "category": tx.category,
                    "percent": round(new_pct, 1),
                    "message": (
                        f"Heads up: {tx.category} budget is at {new_pct:.0f}% "
                        f"({format_indian_currency(new_spent, self.currency_symbol)} / "
                        f"{format_indian_currency(limit_paise, self.currency_symbol)})."
                    ),
                }

        payload = {"transaction": tx, "budget_alert": budget_alert}
        self._notify("transaction_added", payload)
        return payload

    def delete_transaction(self, tx_id: str) -> Transaction | None:
        """Delete a transaction by ID and return the deleted record (for 5s Undo toast)."""
        tx = self._tx_by_id.pop(tx_id, None)
        if tx is None:
            return None
        self._transactions = [t for t in self._transactions if t.id != tx_id]
        self._invalidate_cache()
        self._notify("transaction_deleted", {"transaction": tx})
        return tx

    def restore_transaction(self, tx: Transaction) -> None:
        """Restore a previously deleted transaction (Undo handler)."""
        if tx.id not in self._tx_by_id:
            self._transactions.append(tx)
            self._tx_by_id[tx.id] = tx
            self._invalidate_cache()
            self._notify("transaction_restored", {"transaction": tx})

    # -------------------- Budget CRUD --------------------

    def set_budget(self, category: str, monthly_limit_paise: int) -> Budget:
        """Create or update a monthly budget limit for a category."""
        cleaned = category.strip()
        if not cleaned:
            raise ValueError("Category is required.")
        if monthly_limit_paise < 0:
            raise ValueError("Monthly limit cannot be negative.")
        if (
            cleaned not in EXPENSE_CATEGORIES
            and cleaned not in self._custom_categories
        ):
            self._custom_categories.append(cleaned)

        budget = Budget(category=cleaned, monthly_limit_paise=monthly_limit_paise)
        self._budgets[cleaned] = budget
        self._notify("budget_updated", {"budget": budget})
        return budget

    def delete_budget(self, category: str) -> bool:
        """
        Delete a category budget. Safe even if transactions exist in that category
        (transactions remain intact; only the monthly limit cap is removed).
        """
        removed = self._budgets.pop(category, None)
        if removed is not None:
            self._notify("budget_deleted", {"category": category})
            return True
        return False

    def get_budgets(self) -> list[Budget]:
        """Return all configured budgets sorted by category name."""
        return sorted(self._budgets.values(), key=lambda b: b.category.lower())

    def get_budget_statuses(self, month: str | None = None) -> list[BudgetStatus]:
        """
        Compute BudgetStatus for every configured budget in the given YYYY-MM month.
        Handles zero-limit budgets gracefully without ZeroDivisionError.
        """
        self._ensure_cache()
        target_month = month or self.get_latest_month()
        cat_Totals = self._monthly_category_expense.get(target_month, {})

        statuses: list[BudgetStatus] = []
        for budget in self._budgets.values():
            spent = cat_Totals.get(budget.category, 0)
            limit_p = budget.monthly_limit_paise
            remaining = limit_p - spent
            if limit_p == 0:
                pct = 100.0 if spent > 0 else 0.0
            else:
                pct = (spent / limit_p) * 100.0

            if pct >= 100.0:
                level = "danger"
            elif pct >= 70.0:
                level = "warning"
            else:
                level = "ok"

            statuses.append(
                BudgetStatus(
                    category=budget.category,
                    limit_paise=limit_p,
                    spent_paise=spent,
                    remaining_paise=remaining,
                    percent_used=pct,
                    level=level,
                )
            )

        statuses.sort(key=lambda s: s.percent_used, reverse=True)
        return statuses

    # -------------------- Aggregations & Analytics --------------------

    def get_available_months(self) -> list[str]:
        """Return sorted list of YYYY-MM strings present in store."""
        self._ensure_cache()
        return list(self._available_months)

    def get_latest_month(self) -> str:
        """Return the most recent YYYY-MM month in the dataset (or current month)."""
        self._ensure_cache()
        return (
            self._available_months[0]
            if self._available_months
            else date.today().strftime("%Y-%m")
        )

    def get_summary_metrics(self, month: str | None = None) -> dict[str, int | float]:
        """
        Return Total Balance, Income, Expenses, and Savings Rate (%).
        If `month` is None or 'ALL', returns all-time totals; otherwise for that month.
        Safely handles zero income without division errors.
        """
        self._ensure_cache()
        if month is None or month == "ALL":
            inc = self._total_income_paise
            exp = self._total_expense_paise
        else:
            inc = self._monthly_income.get(month, 0)
            exp = self._monthly_expense.get(month, 0)

        balance = inc - exp
        if inc <= 0:
            savings_rate = 0.0
        else:
            savings_rate = max(-100.0, ((inc - exp) / inc) * 100.0)

        return {
            "balance_paise": balance,
            "income_paise": inc,
            "expense_paise": exp,
            "savings_rate": round(savings_rate, 1),
        }

    @staticmethod
    def previous_month_key(month_key: str) -> str:
        """Given YYYY-MM, return the previous month's YYYY-MM string."""
        year, mon = map(int, month_key.split("-"))
        if mon == 1:
            return f"{year - 1:04d}-12"
        return f"{year:04d}-{mon - 1:02d}"

    def get_monthly_comparison(self, month: str | None = None) -> MonthlyComparison:
        """Compare selected month against its immediately preceding month."""
        self._ensure_cache()
        curr_m = month or self.get_latest_month()
        prev_m = self.previous_month_key(curr_m)

        c_inc = self._monthly_income.get(curr_m, 0)
        p_inc = self._monthly_income.get(prev_m, 0)
        c_exp = self._monthly_expense.get(curr_m, 0)
        p_exp = self._monthly_expense.get(prev_m, 0)

        if p_exp == 0:
            pct_change = None
        else:
            pct_change = ((c_exp - p_exp) / p_exp) * 100.0

        return MonthlyComparison(
            current_month=curr_m,
            previous_month=prev_m,
            current_income_paise=c_inc,
            previous_income_paise=p_inc,
            current_expense_paise=c_exp,
            previous_expense_paise=p_exp,
            expense_change_pct=pct_change,
        )

    def get_last_n_months_series(
        self, n: int = 6, end_month: str | None = None
    ) -> list[dict[str, Any]]:
        """Return chronological list of the last `n` months with income & expense totals."""
        self._ensure_cache()
        curr = end_month or self.get_latest_month()
        months: list[str] = []
        cursor = curr
        for _ in range(n):
            months.append(cursor)
            cursor = self.previous_month_key(cursor)
        months.reverse()

        series: list[dict[str, Any]] = []
        for m in months:
            year, mon = map(int, m.split("-"))
            label = f"{calendar.month_abbr[mon]} '{str(year)[2:]}"
            series.append(
                {
                    "month": m,
                    "label": label,
                    "income_paise": self._monthly_income.get(m, 0),
                    "expense_paise": self._monthly_expense.get(m, 0),
                }
            )
        return series

    def get_category_breakdown(self, month: str) -> list[dict[str, Any]]:
        """Return expense breakdown by category for a month, sorted highest first."""
        self._ensure_cache()
        cat_map = self._monthly_category_expense.get(month, {})
        total = sum(cat_map.values())
        items: list[dict[str, Any]] = []
        for cat, amt in cat_map.items():
            if amt <= 0:
                continue
            pct = (amt / total * 100.0) if total > 0 else 0.0
            items.append(
                {
                    "category": cat,
                    "amount_paise": amt,
                    "percentage": round(pct, 1),
                }
            )
        items.sort(key=lambda x: x["amount_paise"], reverse=True)
        return items

    def get_daily_cumulative_spend(self, month: str) -> list[dict[str, Any]]:
        """Return daily and cumulative spending series for the given YYYY-MM month."""
        self._ensure_cache()
        year, mon = map(int, month.split("-"))
        days_in_month = calendar.monthrange(year, mon)[1]
        day_map = self._monthly_daily_expense.get(month, {})

        cumulative = 0
        series: list[dict[str, Any]] = []
        for d in range(1, days_in_month + 1):
            daily = day_map.get(d, 0)
            cumulative += daily
            series.append(
                {
                    "day": d,
                    "daily_paise": daily,
                    "cumulative_paise": cumulative,
                }
            )
        return series

    def get_computed_insights(self, month: str) -> list[str]:
        """
        Compute dynamic natural-language insights for the Analytics view.
        Example: 'Food is 38% of your spending, 12% higher than last month.'
        """
        self._ensure_cache()
        breakdown = self.get_category_breakdown(month)
        if not breakdown:
            return ["No expenses recorded for this month yet. Add transactions to unlock insights."]

        insights: list[str] = []
        top = breakdown[0]
        top_cat = top["category"]
        top_pct = top["percentage"]
        prev_m = self.previous_month_key(month)
        prev_cat_amt = self._monthly_category_expense.get(prev_m, {}).get(top_cat, 0)
        curr_cat_amt = top["amount_paise"]

        if prev_cat_amt > 0:
            diff_pct = ((curr_cat_amt - prev_cat_amt) / prev_cat_amt) * 100.0
            direction = "higher" if diff_pct >= 0 else "lower"
            insights.append(
                f"{top_cat} is {top_pct:.0f}% of your spending, "
                f"{abs(diff_pct):.0f}% {direction} than last month."
            )
        else:
            insights.append(
                f"{top_cat} is your largest expense at {top_pct:.0f}% "
                f"({format_indian_currency(curr_cat_amt, self.currency_symbol)}) this month."
            )

        metrics = self.get_summary_metrics(month)
        sr = float(metrics["savings_rate"])
        inc = int(metrics["income_paise"])
        exp = int(metrics["expense_paise"])
        if inc > 0:
            if sr >= 25.0:
                insights.append(
                    f"Strong savings discipline: you saved {sr:.1f}% of your income "
                    f"({format_indian_currency(inc - exp, self.currency_symbol)} net positive)."
                )
            elif sr >= 0:
                insights.append(
                    f"Your savings rate is {sr:.1f}% this month. Reducing {top_cat} by 15% "
                    f"would save {format_indian_currency(int(curr_cat_amt * 0.15), self.currency_symbol)}."
                )
            else:
                insights.append(
                    f"Expenses exceeded income by {format_indian_currency(exp - inc, self.currency_symbol)} "
                    f"this month."
                )

        statuses = self.get_budget_statuses(month)
        over_budget = [s for s in statuses if s.level == "danger"]
        if over_budget:
            names = ", ".join(s.category for s in over_budget[:2])
            insights.append(
                f"{len(over_budget)} budget category ({names}) has crossed 100% of its monthly limit."
            )
        elif statuses:
            insights.append(
                f"All {len(statuses)} tracked budget categories are within their monthly limits."
            )

        return insights

    # -------------------- Bulk & Persistence Operations --------------------

    def load_seed_data(
        self, transactions: list[Transaction], budgets: list[Budget]
    ) -> None:
        """Replace current session data with demo seed dataset and notify views."""
        self._transactions = list(transactions)
        self._tx_by_id = {t.id: t for t in self._transactions}
        self._budgets = {b.category: b for b in budgets}
        self._invalidate_cache()
        self._notify("data_reset", {"count": len(self._transactions)})

    def clear_all_data(self) -> None:
        """Clear all transactions and budgets from memory and notify views."""
        self._transactions.clear()
        self._tx_by_id.clear()
        self._budgets.clear()
        self._invalidate_cache()
        self._notify("data_cleared", {})

    def to_json_dict(self) -> dict[str, Any]:
        """Serialize entire store state to a JSON-ready dictionary."""
        return {
            "version": 1,
            "currency_symbol": self.currency_symbol,
            "custom_categories": self._custom_categories,
            "transactions": [t.to_dict() for t in self._transactions],
            "budgets": [b.to_dict() for b in self._budgets.values()],
        }

    def save_to_disk_sync(self, path: str | Path | None = None) -> tuple[bool, str]:
        """Synchronously save data to JSON file with safe error handling."""
        target = Path(path) if path else self.storage_path
        with self._io_lock:
            try:
                payload = self.to_json_dict()
                tmp_path = target.with_suffix(".tmp")
                tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                tmp_path.replace(target)
                return True, f"Saved {len(self._transactions)} transactions to {target.name}."
            except OSError as exc:
                return False, f"Could not save data file: {exc}"

    def save_to_disk_async(
        self,
        on_complete: Callable[[bool, str], None] | None = None,
        path: str | Path | None = None,
    ) -> None:
        """
        Section 5 Rule 9: Run file I/O on a background worker thread so the UI thread
        never blocks.
        """
        def worker() -> None:
            ok, msg = self.save_to_disk_sync(path)
            if on_complete is not None:
                on_complete(ok, msg)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def load_from_disk_sync(self, path: str | Path | None = None) -> tuple[bool, str]:
        """Load state from JSON file with safe error handling and schema validation."""
        target = Path(path) if path else self.storage_path
        if not target.exists():
            return False, "No saved data file found; starting with demo data."

        with self._io_lock:
            try:
                raw = json.loads(target.read_text(encoding="utf-8"))
                tx_list = [Transaction.from_dict(item) for item in raw.get("transactions", [])]
                b_list = [Budget.from_dict(item) for item in raw.get("budgets", [])]
                self.currency_symbol = str(raw.get("currency_symbol", "₹"))
                self._custom_categories = [
                    str(c) for c in raw.get("custom_categories", [])
                ]
                self._transactions = tx_list
                self._tx_by_id = {t.id: t for t in tx_list}
                self._budgets = {b.category: b for b in b_list}
                self._invalidate_cache()
                self._notify("data_loaded", {"count": len(tx_list)})
                return True, f"Loaded {len(tx_list)} transactions from {target.name}."
            except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
                return False, f"Failed to read {target.name}: {exc}"

    def export_csv_async(
        self,
        csv_path: str | Path,
        transactions: list[Transaction],
        on_complete: Callable[[bool, str], None] | None = None,
    ) -> None:
        """Export given transactions list to a CSV file on a worker thread."""
        snapshot = list(transactions)
        target = Path(csv_path)

        def worker() -> None:
            try:
                with target.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        ["ID", "Date", "Type", "Category", "Amount (INR)", "Note"]
                    )
                    for tx in snapshot:
                        writer.writerow(
                            [
                                tx.id,
                                tx.date,
                                tx.type.value,
                                tx.category,
                                f"{tx.amount_paise / 100:.2f}",
                                tx.note,
                            ]
                        )
                if on_complete:
                    on_complete(True, f"Exported {len(snapshot)} rows to {target.name}")
            except OSError as exc:
                if on_complete:
                    on_complete(False, f"CSV export failed: {exc}")

        threading.Thread(target=worker, daemon=True).start()
