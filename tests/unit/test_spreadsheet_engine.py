from packages.application.spreadsheet_engine import detect_spreadsheet_engines


def test_spreadsheet_engine_prefers_excel_when_available():
    paths = {"excel": r"C:\Office\EXCEL.EXE", "soffice": r"C:\LibreOffice\soffice.exe"}

    def which(command):
        return paths.get(command)

    result = detect_spreadsheet_engines(which=which, environ={})
    assert result["status"] == "available"
    assert result["preferred"] == "excel"
    assert set(result["engines"]) == {"excel", "libreoffice"}


def test_spreadsheet_engine_reports_unavailable_without_candidates():
    result = detect_spreadsheet_engines(which=lambda _command: None,
                                        environ={"PROGRAMFILES": "", "PROGRAMFILES(X86)": "",
                                                 "LOCALAPPDATA": ""})
    assert result == {
        "status": "unavailable",
        "engines": {},
        "preferred": None,
        "detail": "未发现 Excel、WPS 或 LibreOffice，暂只能做静态检查",
    }
