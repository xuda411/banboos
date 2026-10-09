from zipfile import ZIP_DEFLATED, ZipFile

from packages.application.financial_release_gate import inspect_workbook_features


def test_inspect_workbook_features_reports_native_features(tmp_path):
    path = tmp_path / "fixture.xlsm"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("xl/tables/table1.xml", "<table/>")
        archive.writestr("xl/externalLinks/externalLink1.xml", "<externalLink/>")
        archive.writestr("xl/connections.xml", "<connections/>")
        archive.writestr("xl/vbaProject.bin", b"fixture")
    # openpyxl cannot load an intentionally minimal archive, so feature
    # inspection is exercised with a real workbook assembled by the package.
    from openpyxl import Workbook

    workbook = Workbook()
    workbook.save(path)
    with ZipFile(path, "a", ZIP_DEFLATED) as archive:
        archive.writestr("xl/tables/table1.xml", "<table/>")
        archive.writestr("xl/externalLinks/externalLink1.xml", "<externalLink/>")
        archive.writestr("xl/connections.xml", "<connections/>")
        archive.writestr("xl/vbaProject.bin", b"fixture")
    report = inspect_workbook_features(path)
    assert report["vba_status"] == "present"
    assert report["excel_table_count"] == 1
    assert report["external_link_count"] == 1
    assert report["connection_count"] == 1
