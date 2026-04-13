# Copyright (c) Siemens 2020
# SPDX-License-Identifier: MIT

from unittest.mock import MagicMock, call, mock_open, patch

from fossology.enums import ReportFormat
from fossology.exceptions import FossologyApiError
from pytest import MonkeyPatch
from sw360 import SW360Error

from fossology_workflow.clearing import Clearing
from fossology_workflow.models import Attachment, Release, ReportStatus
from fossology_workflow.settings import Config


def test_get_upload_report_with_closed_clearing_uploads_both_reports(
    AttachmentObj: Attachment, monkeypatch: MonkeyPatch
):
    logger_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.logger", logger_mock)
    monkeypatch.setattr("fossology_workflow.clearing.sw360.SW360", MagicMock())
    monkeypatch.setattr("fossology_workflow.clearing.Fossology", MagicMock())
    config = Config()
    monkeypatch.setattr(
        "fossology_workflow.clearing.get_release_attachments",
        MagicMock(return_value=([AttachmentObj], "")),
    )

    upload = MagicMock(uploadname="Package", id=1, description="abcd, blah")
    clearing = Clearing(config)
    summary = MagicMock(clearingStatus="Closed", filesToBeCleared=0)
    clearing.foss.upload_summary = MagicMock(return_value=summary)
    clearing.generate_and_download_report = MagicMock(
        return_value=(MagicMock(), "report_name")
    )
    clearing.upload_attachment = MagicMock(return_value=True)
    clearing.get_summary_and_upload_report(upload)
    assert len(clearing.generate_and_download_report.mock_calls) == 2
    assert len(clearing.upload_attachment.mock_calls) == 2


def test_get_upload_report_with_open_clearing_uploads_initial_scan_report(
    AttachmentObj: Attachment, monkeypatch: MonkeyPatch
):
    monkeypatch.setattr("fossology_workflow.clearing.sw360.SW360", MagicMock())
    monkeypatch.setattr("fossology_workflow.clearing.Fossology", MagicMock())
    config = Config()
    monkeypatch.setattr(
        "fossology_workflow.clearing.get_release_attachments",
        MagicMock(return_value=[AttachmentObj]),
    )

    upload = MagicMock(uploadname="Package", id=1, description="abcd, blah")
    clearing = Clearing(config)
    summary = MagicMock(clearingStatus="Open", filesToBeCleared=100)
    clearing.foss.upload_summary = MagicMock(return_value=summary)
    clearing.generate_and_download_report = MagicMock(
        return_value=(MagicMock(), "report_name")
    )
    clearing.upload_attachment = MagicMock()
    clearing.get_summary_and_upload_report(upload)
    assert len(clearing.generate_and_download_report.mock_calls) == 1
    assert len(clearing.upload_attachment.mock_calls) == 2


def test_get_upload_report_with_open_clearing_and_initial_scan_report_does_not_upload_anything(
    AttachmentObj: Attachment,
    monkeypatch: MonkeyPatch,
):
    monkeypatch.setattr("fossology_workflow.clearing.sw360.SW360", MagicMock())
    monkeypatch.setattr("fossology_workflow.clearing.Fossology", MagicMock())
    config = Config()
    attachment = AttachmentObj
    attachment.attachmentType = "INITIAL_SCAN_REPORT"
    monkeypatch.setattr(
        "fossology_workflow.clearing.get_release_attachments",
        MagicMock(return_value=[attachment]),
    )

    upload = MagicMock(uploadname="Package", id=1, description="abcd, blah")
    clearing = Clearing(config)
    summary = MagicMock(clearingStatus="Open", filesToBeCleared=100)
    clearing.foss.upload_summary = MagicMock(return_value=summary)
    clearing.upload_sw360_reports = MagicMock()
    clearing.get_summary_and_upload_report(upload)
    clearing.upload_sw360_reports.assert_not_called()


def test_upload_sw360_reports_uploads_initial_scan_if_clearing_not_closed(
    monkeypatch: MonkeyPatch, ReleaseObj: Release
):
    monkeypatch.setattr("fossology_workflow.clearing.Path", MagicMock())
    monkeypatch.setattr("fossology_workflow.clearing.sw360.SW360", MagicMock())
    monkeypatch.setattr("fossology_workflow.clearing.Fossology", MagicMock())
    config = Config()
    clearing = Clearing(config)

    release = ReleaseObj
    release.fossology_upload = MagicMock(
        uploadname="Package", id=1, description="abcd, blah"
    )
    release.fossology_upload_summary = MagicMock(
        clearingStatus="Open", filesToBeCleared=100
    )
    clearing.foss.download_report = MagicMock(return_value=("1", "report.xml"))
    with patch("fossology_workflow.clearing.open", mock_open()):
        clearing.upload_sw360_reports(release)
    assert (
        call("release_id", "report.xml", upload_type="INITIAL_SCAN_REPORT")
        in clearing.sw360.upload_release_attachment.mock_calls
    )


def test_upload_sw360_reports_does_not_upload_initial_scan_report_if_option_is_not_set(
    AttachmentObj: Attachment, monkeypatch: MonkeyPatch, ReleaseObj: Release
):
    logger_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.logger", logger_mock)
    monkeypatch.setattr("fossology_workflow.clearing.Path", MagicMock())
    monkeypatch.setattr("fossology_workflow.clearing.sw360.SW360", MagicMock())
    monkeypatch.setattr("fossology_workflow.clearing.Fossology", MagicMock())
    config = Config()
    config.UPLOAD_INITIAL_SCAN_REPORT = False
    clearing = Clearing(config)
    clearing.upload_sw360_reports = MagicMock()
    monkeypatch.setattr(
        "fossology_workflow.clearing.get_release_attachments",
        MagicMock(return_value=([AttachmentObj], "")),
    )

    release = ReleaseObj
    release.fossology_upload = MagicMock(
        uploadname="Package", id=1, description="abcd, blah"
    )
    release.fossology_upload_summary = MagicMock(
        clearingStatus="Open", filesToBeCleared=100
    )
    clearing.foss.upload_summary = MagicMock(
        return_value=release.fossology_upload_summary
    )
    clearing.generate_and_download_report = MagicMock(
        return_value=(MagicMock(), "report_name")
    )
    clearing.upload_attachment = MagicMock(return_value=True)
    clearing.get_summary_and_upload_report(release)
    clearing.upload_sw360_reports.assert_not_called()


def test_upload_sw360_reports_uploads_real_reports_if_clearing_is_closed(
    monkeypatch: MonkeyPatch, ReleaseObj: Release
):
    monkeypatch.setattr("fossology_workflow.clearing.Path", MagicMock())
    monkeypatch.setattr("fossology_workflow.clearing.sw360.SW360", MagicMock())
    monkeypatch.setattr("fossology_workflow.clearing.Fossology", MagicMock())
    config = Config()
    clearing = Clearing(config)

    release = ReleaseObj
    release.fossology_upload = MagicMock(
        uploadname="Package", id=1, description="abcd, blah"
    )
    release.fossology_upload_summary = MagicMock(
        clearingStatus="Closed", filesToBeCleared=0
    )
    clearing.foss.download_report = MagicMock(return_value=("1", "report.xml"))
    with patch("fossology_workflow.clearing.open", mock_open()):
        clearing.upload_sw360_reports(release)
    assert (
        call("release_id", "report.xml", upload_type="COMPONENT_LICENSE_INFO_XML")
        in clearing.sw360.upload_release_attachment.mock_calls
    )


def test_generate_and_download_report_sets_error_status_if_fossology_fails_returning_report(
    monkeypatch: MonkeyPatch, ReleaseObj: Release
):
    logger_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.logger", logger_mock)
    monkeypatch.setattr("fossology_workflow.clearing.Path", MagicMock())
    monkeypatch.setattr("fossology_workflow.clearing.sw360.SW360", MagicMock())
    monkeypatch.setattr("fossology_workflow.clearing.Fossology", MagicMock())
    config = Config()
    clearing = Clearing(config)

    release = ReleaseObj
    release.fossology_upload = MagicMock(
        uploadname="Package", id=1, description="abcd, blah"
    )
    response = MagicMock()
    response.json = MagicMock(return_value={"message": "error from api"})
    clearing.foss.generate_report = MagicMock(
        side_effect=FossologyApiError("some error message", response=response)
    )
    clearing.generate_and_download_report(release, ReportFormat.UNIFIEDREPORT)
    assert release.workflow_summary.report_status == ReportStatus.FOSSOLOGY_ERROR
    logger_mock.error.assert_called_once()


def test_get_summary_and_upload_report_sets_error_status_if_fossology_fails_getting_summary(
    monkeypatch: MonkeyPatch, ReleaseObj: Release
):
    logger_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.logger", logger_mock)
    monkeypatch.setattr("fossology_workflow.clearing.Path", MagicMock())
    monkeypatch.setattr("fossology_workflow.clearing.sw360.SW360", MagicMock())
    monkeypatch.setattr("fossology_workflow.clearing.Fossology", MagicMock())
    config = Config()
    clearing = Clearing(config)

    release = ReleaseObj
    release.fossology_upload = MagicMock(
        uploadname="Package", id=1, description="abcd, blah"
    )
    response = MagicMock()
    response.json = MagicMock(return_value={"message": "error from api"})
    clearing.upload_sw360_reports = MagicMock()
    clearing.foss.upload_summary = MagicMock(
        side_effect=FossologyApiError("some error message", response=response)
    )
    clearing.get_summary_and_upload_report(release)
    assert release.workflow_summary.report_status == ReportStatus.FOSSOLOGY_ERROR
    clearing.upload_sw360_reports.assert_not_called()
    logger_mock.error.assert_called_once()


def test_upload_sw360_reports_sets_error_status_if_sw360_exception_is_returned(
    monkeypatch: MonkeyPatch, ReleaseObj: Release
):
    logger_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.logger", logger_mock)
    monkeypatch.setattr("fossology_workflow.clearing.sw360.SW360", MagicMock())
    monkeypatch.setattr("fossology_workflow.clearing.Fossology", MagicMock())
    config = Config()
    clearing = Clearing(config)

    report_content = bytes("This is a clearing report", "UTF-8")
    clearing.generate_and_download_report = MagicMock(
        return_value=(report_content, "report_name")
    )
    release = ReleaseObj
    release.fossology_upload_summary = MagicMock()
    release.fossology_upload_summary.clearingStatus = "Closed"
    clearing.sw360.upload_release_attachment = MagicMock(side_effect=SW360Error())
    clearing.upload_sw360_reports(release)
    assert release.workflow_summary.report_status == ReportStatus.SW360_ERROR
    logger_mock.error.assert_called()

    clearing.project = MagicMock(linked_releases=[release])
    clearing.workflow_metrics()
    assert clearing.report_metric.total == 1
    assert clearing.report_metric.error == 1


def test_upload_sw360_reports_sets_report_status_if_reports_are_uploaded(
    monkeypatch: MonkeyPatch, ReleaseObj: Release
):
    logger_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.logger", logger_mock)
    monkeypatch.setattr("fossology_workflow.clearing.sw360.SW360", MagicMock())
    monkeypatch.setattr("fossology_workflow.clearing.Fossology", MagicMock())
    config = Config()
    clearing = Clearing(config)

    report_content = bytes("This is a clearing report", "UTF-8")
    clearing.generate_and_download_report = MagicMock(
        return_value=(report_content, "report_name")
    )
    release = ReleaseObj
    release.fossology_upload_summary = MagicMock()
    release.fossology_upload_summary.clearingStatus = "Closed"
    clearing.sw360.upload_release_attachment = MagicMock()
    clearing.upload_sw360_reports(release)
    assert release.workflow_summary.report_status == ReportStatus.UPLOADED
    logger_mock.info.assert_called()

    clearing.project = MagicMock(linked_releases=[release])
    clearing.workflow_metrics()
    assert clearing.report_metric.total == 1
    assert clearing.report_metric.uploaded == 1
