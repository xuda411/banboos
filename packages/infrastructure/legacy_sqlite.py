"""Read-only adapter for an isolated Banboos 1.6.6 SQLite copy."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .database_fields import PRICE_FIELDS


class LegacyDatabaseError(RuntimeError):
    pass


class LegacySQLiteReader:
    """Expose stable query methods without allowing writes to the legacy DB."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        if not self.path.is_file():
            raise LegacyDatabaseError(f"legacy database not found: {self.path}")
        if self.path.name == "price_analysis.db" and self.path.parent.name == "data":
            raise LegacyDatabaseError("refusing the 1.6.6 production default database; use an isolated copy")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def list_nodes(self, province: str | None = None, query: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if province:
            clauses.append("province = ?")
            params.append(province)
        if query:
            clauses.append("node_name LIKE ?")
            params.append(f"%{query}%")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT id, node_name, province FROM nodes{where} ORDER BY province, node_name",
                params,
            ).fetchall()
        return [dict(id=row["id"], name=row["node_name"], province=row["province"] or "") for row in rows]

    def node_count(self) -> int:
        with closing(self._connect()) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM nodes").fetchone()[0])

    def price_summary(self, node_id: int, market: str, start_date: date, end_date: date) -> dict[str, Any]:
        if market not in {"日前", "实时"}:
            raise ValueError("market must be 日前 or 实时")
        if end_date < start_date:
            raise ValueError("end_date must not precede start_date")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT run_date, source_file, " + ",".join(PRICE_FIELDS) +
                " FROM price_data WHERE node_id=? AND case_type=? AND run_date>=? AND run_date<=? "
                " ORDER BY run_date, id",
                (node_id, market, start_date.isoformat(), end_date.isoformat()),
            ).fetchall()
        valid = []
        for row in rows:
            if all(value is not None for value in row[2:]) and all(_is_finite(value) for value in row[2:]):
                valid.append(row)
        dates = [date.fromisoformat(str(row["run_date"])[:10]) for row in valid]
        return dict(
            node_id=node_id,
            market=market,
            start_date=start_date,
            end_date=end_date,
            valid_days=len(valid),
            data_points=len(valid) * len(PRICE_FIELDS),
            first_date=min(dates) if dates else None,
            last_date=max(dates) if dates else None,
            sources=sorted({str(row["source_file"] or "") for row in valid if row["source_file"]}),
            source_mode="legacy-readonly",
        )

    def price_range(self, node_id: int, market: str) -> dict[str, Any]:
        if market not in {"日前", "实时"}:
            raise ValueError("market must be 日前 or 实时")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT run_date, " + ",".join(PRICE_FIELDS) +
                " FROM price_data WHERE node_id=? AND case_type=? ORDER BY run_date, id",
                (node_id, market),
            ).fetchall()
        dates: list[date] = []
        for row in rows:
            values = row[1:]
            if all(value is not None and _is_finite(value) for value in values):
                dates.append(date.fromisoformat(str(row[0])[:10]))
        return dict(node_id=node_id, market=market,
                    first_date=min(dates) if dates else None,
                    last_date=max(dates) if dates else None,
                    source_mode="legacy-readonly")

    def weather_summary(self, node_id: int, start_time: datetime | None = None,
                        end_time: datetime | None = None) -> dict[str, Any]:
        start_text = start_time.isoformat(sep=" ") if start_time else "0000-01-01"
        end_text = end_time.isoformat(sep=" ") if end_time else "9999-12-31"
        with self._connect() as conn:
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='node_meteorology_data'"
            ).fetchone()
            if not table:
                return dict(node_id=node_id, observations=0, source_mode="legacy-readonly")
            rows = conn.execute(
                "SELECT data_time, source, ghi, wind_speed_100m, temp FROM node_meteorology_data "
                "WHERE node_id=? AND data_time>=? AND data_time<=? AND COALESCE(is_outlier,0)=0 "
                "ORDER BY data_time",
                (node_id, start_text, end_text),
            ).fetchall()
        def mean(field: str) -> float | None:
            values = [float(row[field]) for row in rows if row[field] is not None and _is_finite(row[field])]
            return sum(values) / len(values) if values else None
        timestamps = [datetime.fromisoformat(str(row["data_time"])) for row in rows]
        return dict(
            node_id=node_id,
            start_time=min(timestamps) if timestamps else None,
            end_time=max(timestamps) if timestamps else None,
            observations=len(rows),
            source=rows[0]["source"] if rows and rows[0]["source"] else None,
            avg_ghi_w_m2=mean("ghi"),
            avg_wind_speed_m_s=mean("wind_speed_100m"),
            avg_temp_c=mean("temp"),
            source_mode="legacy-readonly",
        )

    def weather_observations(self, node_id: int, start_time: datetime | None = None,
                             end_time: datetime | None = None, limit: int = 744) -> list[dict[str, Any]]:
        if not 1 <= limit <= 744:
            raise ValueError("limit must be between 1 and 744")
        start_text = start_time.isoformat(sep=" ") if start_time else "0000-01-01"
        end_text = end_time.isoformat(sep=" ") if end_time else "9999-12-31"
        with self._connect() as conn:
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='node_meteorology_data'"
            ).fetchone()
            if not table:
                return []
            rows = conn.execute(
                "SELECT data_time, source, ghi, wind_speed_100m, temp "
                "FROM node_meteorology_data WHERE node_id=? AND data_time>=? AND data_time<=? "
                "AND COALESCE(is_outlier,0)=0 ORDER BY data_time LIMIT ?",
                (node_id, start_text, end_text, limit),
            ).fetchall()
        return [dict(data_time=datetime.fromisoformat(str(row["data_time"])),
                     source=row["source"], ghi_w_m2=row["ghi"],
                     wind_speed_m_s=row["wind_speed_100m"], temp_c=row["temp"])
                for row in rows]

    def quality_summary(self, node_id: int, market: str, start_date: date,
                        end_date: date) -> dict[str, Any]:
        if market not in {"日前", "实时"}:
            raise ValueError("market must be 日前 or 实时")
        if end_date < start_date:
            raise ValueError("end_date must not precede start_date")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT " + ",".join(PRICE_FIELDS) +
                " FROM price_data WHERE node_id=? AND case_type=? AND run_date>=? AND run_date<=?",
                (node_id, market, start_date.isoformat(), end_date.isoformat()),
            ).fetchall()
        missing = non_finite = complete = 0
        for row in rows:
            row_missing = row_non_finite = 0
            for value in row:
                if value is None:
                    row_missing += 1
                elif not _is_finite(value):
                    row_non_finite += 1
            missing += row_missing
            non_finite += row_non_finite
            if row_missing == 0 and row_non_finite == 0:
                complete += 1
        total = len(rows)
        return {
            "node_id": node_id,
            "market": market,
            "start_date": start_date,
            "end_date": end_date,
            "total_records": total,
            "complete_records": complete,
            "incomplete_records": total - complete,
            "missing_cells": missing,
            "non_finite_cells": non_finite,
            "coverage_ratio": complete / total if total else 0.0,
            "source_mode": "legacy-readonly",
        }

    def price_curves(self, node_id: int, market: str, start_date: date,
                     end_date: date) -> list[dict[str, Any]]:
        """Return complete daily 96-point curves for an analysis worker."""
        if market not in {"日前", "实时"}:
            raise ValueError("market must be 日前 or 实时")
        if end_date < start_date:
            raise ValueError("end_date must not precede start_date")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT run_date, " + ",".join(PRICE_FIELDS) +
                " FROM price_data WHERE node_id=? AND case_type=? AND run_date>=? AND run_date<=?"
                " ORDER BY run_date, id",
                (node_id, market, start_date.isoformat(), end_date.isoformat()),
            ).fetchall()
        curves: list[dict[str, Any]] = []
        seen_dates: set[str] = set()
        for row in rows:
            values = list(row[1:])
            run_date = str(row[0])[:10]
            if run_date in seen_dates or len(values) != len(PRICE_FIELDS):
                continue
            if all(value is not None and _is_finite(value) for value in values):
                curves.append({"run_date": run_date, "prices": [float(value) for value in values]})
                seen_dates.add(run_date)
        return curves


def _is_finite(value: Any) -> bool:
    try:
        return bool(float(value) == float(value)) and abs(float(value)) != float("inf")
    except (TypeError, ValueError):
        return False
