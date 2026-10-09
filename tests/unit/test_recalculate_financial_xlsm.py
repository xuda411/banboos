from pathlib import Path

from scripts.recalculate_financial_xlsm import recalculate


def test_recalculate_rejects_in_place_and_non_xlsm(tmp_path):
    source = tmp_path / "source.xlsm"
    source.write_bytes(b"placeholder")
    try:
        recalculate(source, source)
    except ValueError as error:
        assert "不能覆盖" in str(error)
    else:
        raise AssertionError("expected in-place recalculation rejection")


def test_recalculate_reports_missing_source(tmp_path):
    missing = tmp_path / "missing.xlsm"
    try:
        recalculate(missing, tmp_path / "out.xlsm")
    except FileNotFoundError as error:
        assert Path(error.args[0]) == missing.resolve()
    else:
        raise AssertionError("expected missing source rejection")
