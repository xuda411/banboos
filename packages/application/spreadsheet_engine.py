"""Detect a native spreadsheet engine for final XLSM recalculation checks."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path

from openpyxl import load_workbook

EngineLocator = Callable[[str], str | None]


def detect_spreadsheet_engines(
    which: EngineLocator | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Return available Excel/WPS/LibreOffice executables without launching them."""
    locate = which or shutil.which
    env = environ or os.environ
    candidates: dict[str, list[str]] = {
        "excel": ["excel", "EXCEL.EXE"],
        "wps": ["wps", "et", "wps.exe", "et.exe"],
        "libreoffice": ["soffice", "libreoffice"],
    }
    found: dict[str, str] = {}
    for name, commands in candidates.items():
        for command in commands:
            path = locate(command)
            if path:
                found[name] = str(Path(path).resolve())
                break
    # Windows installations are often not on PATH. Probe the conventional
    # locations, while keeping this function read-only and side-effect free.
    roots = [env.get("PROGRAMFILES"), env.get("PROGRAMFILES(X86)"), env.get("LOCALAPPDATA")]
    patterns = {
        "excel": ("Microsoft Office", "root", "Office16", "EXCEL.EXE"),
        "wps": ("Kingsoft", "WPS Office", "ksolaunch.exe"),
    }
    for name, parts in patterns.items():
        if name in found:
            continue
        for root in filter(None, roots):
            candidate = Path(root).joinpath(*parts)
            if candidate.is_file():
                found[name] = str(candidate.resolve())
                break
    available = list(found)
    return {
        "status": "available" if available else "unavailable",
        "engines": found,
        "preferred": next((name for name in ("excel", "wps", "libreoffice") if name in found), None),
        "detail": "可执行原生重算" if available else "未发现 Excel、WPS 或 LibreOffice，暂只能做静态检查",
    }


_EXCEL_RECALC_SCRIPT = r'''
param([string]$WorkbookPath)
$ErrorActionPreference = "Stop"
$excel = $null
$book = $null
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $book = $excel.Workbooks.Open($WorkbookPath, $false, $false)
    $excel.CalculateFullRebuild()
    $book.Save()
    $book.Close($true)
    $book = $null
    $excel.Quit()
} finally {
    if ($book -ne $null) { $book.Close($false) }
    if ($excel -ne $null) { $excel.Quit() }
    if ($book -ne $null) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($book) }
    if ($excel -ne $null) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($excel) }
}
'''


def recalculate_xlsm(source: str | Path, destination: str | Path,
                     timeout_seconds: int = 180) -> dict[str, object]:
    """Copy an XLSM and recalculate it with installed Excel when available.

    The source is never opened for writing.  A missing native engine is a
    first-class result so callers can fall back to static formula inspection.
    """
    source_path = Path(source).expanduser().resolve()
    destination_path = Path(destination).expanduser().resolve()
    if source_path.suffix.lower() != ".xlsm" or destination_path.suffix.lower() != ".xlsm":
        raise ValueError("原生重算只接受 .xlsm 文件")
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if source_path == destination_path:
        raise ValueError("原生重算目标不能覆盖源模板")
    engine = detect_spreadsheet_engines()
    if engine["preferred"] != "excel":
        return {"status": "unavailable", "engine": engine,
                "source": str(source_path), "destination": str(destination_path)}
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, destination_path)
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", encoding="utf-8", delete=False) as stream:
        script = Path(stream.name)
        stream.write(_EXCEL_RECALC_SCRIPT)
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(script), "-WorkbookPath", str(destination_path)],
            check=True, capture_output=True, text=True, timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError) as error:
        destination_path.unlink(missing_ok=True)
        return {"status": "failed", "engine": engine, "source": str(source_path),
                "destination": str(destination_path),
                "error": f"{type(error).__name__}: {error}"}
    finally:
        script.unlink(missing_ok=True)
    workbook = load_workbook(destination_path, data_only=True, keep_vba=True, read_only=True)
    try:
        cached_checks = {
            "financial_irr": workbook["财务指标"]["D78"].value,
            "financial_npv_wan": workbook["财务指标"]["D79"].value,
            "first_year_project_cashflow_wan": workbook["财务指标"]["E76"].value,
            "first_year_equity_cashflow_wan": workbook["财务指标"]["E63"].value,
        }
    finally:
        workbook.close()
    return {"status": "recalculated", "engine": engine, "source": str(source_path),
            "destination": str(destination_path), "cached_checks": cached_checks}
