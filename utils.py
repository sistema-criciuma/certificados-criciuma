from __future__ import annotations

import io
from datetime import date, datetime
from typing import Any

import pandas as pd


def normalize_cpf(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def mask_cpf(value: Any) -> str:
    cpf = normalize_cpf(value)
    if len(cpf) != 11:
        return cpf
    return f"{cpf[:3]}.***.***-{cpf[-2:]}"


def parse_date_like(value: Any) -> date | None:
    if value in (None, "", "NaT"):
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()

    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def ensure_iso_date_string(value: Any) -> str:
    parsed = parse_date_like(value)
    if not parsed:
        raise ValueError(f"Data inválida: {value}")
    return parsed.strftime("%Y-%m-%d")


def format_date_br(value: Any) -> str:
    parsed = parse_date_like(value)
    if not parsed:
        return str(value or "")
    return parsed.strftime("%d/%m/%Y")


def parse_carga_horaria_input(value: Any) -> float:
    raw = str(value or "").strip().replace(" ", "")
    if not raw:
        raise ValueError("Carga horária obrigatória.")
    raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError("Carga horária inválida. Use formatos como 20 ou 20,5.") from exc


def format_carga_horaria_display(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        num = float(str(value).replace(",", "."))
    except ValueError:
        return str(value)
    if num.is_integer():
        return str(int(num))
    return str(num).replace(".", ",")


def records_to_dataframe(records: list[dict[str, Any]], preferred_columns: list[str] | None = None) -> pd.DataFrame:
    df = pd.DataFrame(records or [])
    if preferred_columns:
        cols = [c for c in preferred_columns if c in df.columns]
        if cols:
            df = df[cols]
    return df


def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return output.getvalue()


def empty_lote_template_bytes() -> bytes:
    return dataframe_to_excel_bytes(pd.DataFrame(columns=["nome", "cpf"]))


def get_public_course_date_bounds(cursos: list[dict[str, Any]]) -> tuple[date, date]:
    dates = [parse_date_like(c.get("conclusao")) for c in cursos]
    dates = [d for d in dates if d]
    today = date.today()
    if not dates:
        return today, today
    return min(dates), max(dates)
