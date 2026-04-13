# Copyright (c) Siemens 2020
# SPDX-License-Identifier: MIT

from typing import Any
from unittest.mock import MagicMock, call

import pytest
from click.testing import CliRunner
from fossology.exceptions import FossologyApiError
from sw360 import SW360Error

from fossology_workflow.__main__ import create_initial_reports, request_clearing
from fossology_workflow.clearing import Clearing
from fossology_workflow.helpers import estimate_clearing_effort, get_clearing_complexity
from fossology_workflow.models import (
    Project,
    Release,
    ReportStatus,
    UploadStatus,
)


@pytest.fixture
def SW360Project():
    return {
        "id": "1234",
        "name": "sw360project",
        "clearingRequestId": "CR-007",
        "linkedReleases": [
            {
                "release": "release_id",
            },
        ],
    }


@pytest.fixture
def ReleaseData():
    return {
        "id": "release_id",
        "name": "my_release_name",
        "version": "0.0.1",
        "_links": {"sw360:component": {"href": "component/url"}},
    }


def test_get_clearing_complexity():
    assert get_clearing_complexity("Hello") == "Invalid number"
    assert get_clearing_complexity("50") == "VERY_SMALL"
    assert get_clearing_complexity("500") == "SMALL"
    assert get_clearing_complexity("3000") == "MEDIUM"
    assert get_clearing_complexity("8000") == "LARGE"
    assert get_clearing_complexity("15000") == "VERY_LARGE"


def test_estimate_clearing_effort():
    assert estimate_clearing_effort(50) == 0.5
    assert estimate_clearing_effort(500) == 2
    assert estimate_clearing_effort(3000) == 5
    assert estimate_clearing_effort(8000) == 12
    assert estimate_clearing_effort(15000) == 20


def test_cli_request_clearing_gets_env_variables(monkeypatch, ClearingObj):
    ClearingObj.get_sw360_project = MagicMock()
    ClearingObj.upload_sources = MagicMock()
    ClearingObj.upload_reports = MagicMock()
    monkeypatch.setattr(
        "fossology_workflow.__main__.Clearing", MagicMock(return_value=ClearingObj)
    )
    runner = CliRunner()
    runner.invoke(request_clearing)
    assert not ClearingObj.sw360_project
    assert ClearingObj.sw360_cr
    ClearingObj.get_sw360_project.assert_called_once()
    ClearingObj.upload_sources.assert_called_once()
    ClearingObj.upload_reports.assert_called_once()


def test_cli_request_clearing_if_none_of_cr_or_project_is_set_exits(
    monkeypatch, env_without_clearing_info, ClearingObj
):
    ClearingObj.get_sw360_project = MagicMock()
    ClearingObj.upload_sources = MagicMock()
    ClearingObj.upload_reports = MagicMock()
    ClearingObj.sw360_cr = None
    ClearingObj.sw360_project = None
    monkeypatch.setattr(
        "fossology_workflow.__main__.Clearing", MagicMock(return_value=ClearingObj)
    )
    runner = CliRunner()
    runner.invoke(request_clearing)
    ClearingObj.get_sw360_project.assert_not_called()
    ClearingObj.upload_sources.assert_not_called()
    ClearingObj.upload_reports.assert_not_called()


def test_cli_create_initial_clearing_calls_get_releases(monkeypatch, ClearingObj):
    ClearingObj.get_sw360_project = MagicMock()
    ClearingObj.get_last_releases = MagicMock()
    monkeypatch.setattr(
        "fossology_workflow.__main__.Clearing", MagicMock(return_value=ClearingObj)
    )
    runner = CliRunner()
    runner.invoke(create_initial_reports)
    ClearingObj.get_sw360_project.assert_not_called()
    ClearingObj.get_last_releases.assert_called_once()


def test_get_sw360_project_returns_project_and_releases(
    ClearingObj, SW360Project, ReleaseData
):
    ClearingObj.sw360.get_component_by_url = MagicMock(
        return_value={"componentType": "OSS"}
    )
    ClearingObj.sw360.get_project = MagicMock(return_value=SW360Project)
    ClearingObj.sw360.get_release = MagicMock(return_value=ReleaseData)
    ClearingObj.get_sw360_project()
    assert ClearingObj.project.clearingRequestId == "CR-007"
    assert len(ClearingObj.project.linked_releases) == 1


def test_get_sw360_project_skip_release_if_component_is_not_oss(
    ClearingObj: Clearing, SW360Project: Any, ReleaseData: dict
):
    ClearingObj.sw360.get_component_by_url = MagicMock(
        return_value={"componentType": "INNER_SOURCE"}
    )
    ClearingObj.sw360.get_project = MagicMock(return_value=SW360Project)
    ClearingObj.sw360.get_release = MagicMock(return_value=ReleaseData)
    ClearingObj.get_sw360_project()
    assert ClearingObj.project.clearingRequestId == "CR-007"
    assert len(ClearingObj.project.linked_releases) == 1
    assert ClearingObj.project.linked_releases[0].skip_upload
    assert (
        ClearingObj.project.linked_releases[0].workflow_summary.upload_status
        == UploadStatus.NOT_OSS
    )


def test_get_sw360_project_skip_release_if_component_has_already_been_scanned(
    ClearingObj: Clearing, SW360Project: Any, ReleaseData: dict
):
    ClearingObj.sw360.get_component_by_url = MagicMock(
        return_value={"componentType": "INNER_SOURCE"}
    )
    ReleaseData["clearingState"] = "REPORT_AVAILABLE"
    ClearingObj.sw360.get_project = MagicMock(return_value=SW360Project)
    ClearingObj.sw360.get_release = MagicMock(return_value=ReleaseData)
    ClearingObj.get_sw360_project()
    assert len(ClearingObj.project.linked_releases) == 1
    assert ClearingObj.project.linked_releases[0].skip_upload
    assert (
        ClearingObj.project.linked_releases[0].workflow_summary.upload_status
        == UploadStatus.ALREADY_SCANNED
    )


def test_get_get_project_releases_skips_release_if_it_already_exists(
    ClearingObj: Clearing,
    SW360Project: dict,
    ReleaseObj: Release,
    monkeypatch: pytest.MonkeyPatch,
):
    logger_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.logger", logger_mock)
    ClearingObj.project.data = SW360Project
    ClearingObj.project.id = "project_id"
    ClearingObj.project.linked_releases = [ReleaseObj]
    ClearingObj.get_releases()
    assert len(ClearingObj.project.linked_releases) == 1
    assert (
        call("Release release_id already exists in project project_id.")
        in logger_mock.info.mock_calls
    )


def test_is_oss_component_returns_true(
    ClearingObj: Clearing, ReleaseObj: Release, ReleaseData: dict
):
    ClearingObj.sw360.get_component_by_url = MagicMock(
        return_value={"componentType": "OSS"}
    )
    ReleaseObj.data = ReleaseData
    assert ClearingObj.is_oss_component(ReleaseObj)


def test_is_oss_component_returns_false_if_sw360_error_occurred(
    ClearingObj: Clearing, ReleaseObj: Release, ReleaseData: dict
):
    ClearingObj.sw360.get_component_by_url = MagicMock(side_effect=SW360Error)
    release = ReleaseObj
    release.data = ReleaseData
    assert not ClearingObj.is_oss_component(release)
    assert release.workflow_summary.upload_status == UploadStatus.SW360_ERROR


def test_project_model_returns_correct_number_of_uploads_if_fossology_upload_is_filled(
    ReleaseObj: Release,
):
    upload = MagicMock()
    project = Project()
    release = ReleaseObj
    release.fossology_upload = upload
    project.linked_releases = [release]
    assert len(list(filter(lambda x: x.fossology_upload, project.linked_releases))) == 1


def test_project_model_returns_correct_number_of_uploads_if_fossology_upload_is_not_filled(
    ReleaseObj: Release,
):
    project = Project()
    project.linked_releases = [ReleaseObj]
    assert len(list(filter(lambda x: x.fossology_upload, project.linked_releases))) == 0


def test_get_release_source_populates_not_uploaded_data_properly(
    ClearingObj, ReleaseObj, attachment
):
    release = ReleaseObj
    attachment["attachmentType"] = "SOURCE"
    release.data = {"_embedded": {"sw360:attachments": [attachment]}}
    ClearingObj.project = MagicMock(linked_releases=[release])
    ClearingObj.source_already_exists = MagicMock(return_value=(None, False))
    ClearingObj.foss.create_folder = MagicMock()
    ClearingObj.uploads_to_fossology = False
    ClearingObj.get_release_source(release)
    assert release.workflow_summary.upload_status == UploadStatus.DO_NOT_UPLOAD
    ClearingObj.sw360.download_release_attachment.assert_not_called()
    ClearingObj.workflow_metrics()
    assert ClearingObj.upload_metric.ignored == 1


def test_get_release_source_with_ignore_flag(ClearingObj, ReleaseObj, attachment):
    release = ReleaseObj
    attachment["attachmentType"] = "SOURCE"
    release.data = {"_embedded": {"sw360:attachments": [attachment]}}
    release.data["additionalData"] = {"WF:ignore": ""}
    ClearingObj.project = MagicMock(linked_releases=[release])
    ClearingObj.upload_source = MagicMock()
    assert not ClearingObj.get_release_source(release)
    assert release.workflow_summary.upload_status == UploadStatus.IGNORED
    ClearingObj.upload_source.assert_not_called()
    ClearingObj.workflow_metrics()
    assert ClearingObj.upload_metric.ignored == 1


def test_get_release_source_with_default_ignore_flag(
    ClearingObj, ReleaseObj, attachment, monkeypatch
):
    monkeypatch.delenv("IGNORE_FLAG", raising=False)
    release = ReleaseObj
    attachment["attachmentType"] = "SOURCE"
    release.data = {
        "_embedded": {"sw360:attachments": [attachment]},
        "additionalData": {"WF:ignore": ""},
    }
    ClearingObj.project = MagicMock(linked_releases=[release])
    ClearingObj.upload_source = MagicMock()

    assert not ClearingObj.get_release_source(release)
    assert release.workflow_summary.upload_status == UploadStatus.IGNORED
    ClearingObj.upload_source.assert_not_called()


def test_get_release_source_returns_false_if_attachment_is_not_found(
    ClearingObj, ReleaseObj, attachment, monkeypatch
):
    attachment["attachmentType"] = "SOURCE"
    release = ReleaseObj
    release.data = {"_embedded": {"sw360:attachments": [attachment]}}
    ClearingObj.project = MagicMock(linked_releases=[release])
    monkeypatch.setattr(
        "fossology_workflow.clearing.get_release_attachments",
        MagicMock(return_value=None),
    )
    assert not ClearingObj.get_release_source(release)
    assert release.workflow_summary.upload_status == UploadStatus.UNKNOWN
    ClearingObj.workflow_metrics()
    assert ClearingObj.upload_metric.error == 1


def test_workflow_summary_collects_reuse_info(ClearingObj, ReleaseObj, monkeypatch):
    release_reuse_info = ReleaseObj
    release_reuse_info.workflow_summary.reuse_info = "upload (from last date)"
    csv_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.csv", csv_mock)
    ClearingObj.project = MagicMock(linked_releases=[release_reuse_info])
    ClearingObj.workflow_summary()
    assert csv_mock.writer().writerow.mock_calls[1] == call(
        [
            ClearingObj.project.name,
            "my_release_name 0.0.1",
            "",
            "",
            "UNKNOWN",
            "",
            "",
            "",
            "upload (from last date)",
        ]
    )


def test_workflow_summary_collects_unknown_report_status(
    ClearingObj, ReleaseObj, monkeypatch
):
    release_no_report = ReleaseObj
    release_no_report.workflow_summary.report_status = ReportStatus.UNKNOWN
    release_no_report.fossology_upload_summary = MagicMock(
        filesToBeCleared="42", clearingStatus="Open"
    )
    csv_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.csv", csv_mock)
    ClearingObj.project = MagicMock(linked_releases=[release_no_report])
    ClearingObj.workflow_summary()
    assert csv_mock.writer().writerow.mock_calls[1] == call(
        [
            ClearingObj.project.name,
            "my_release_name 0.0.1",
            "",
            "Open",
            "UNKNOWN",
            "42",
            "VERY_SMALL",
            "",
            "",
        ]
    )


def test_workflow_summary_collects_uploaded_report_status(
    ClearingObj, ReleaseObj, monkeypatch
):
    release_with_report = ReleaseObj
    release_with_report.workflow_summary.report_status = ReportStatus.UPLOADED
    csv_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.csv", csv_mock)
    ClearingObj.project = MagicMock(linked_releases=[release_with_report])
    ClearingObj.workflow_summary()
    assert csv_mock.writer().writerow.mock_calls[1] == call(
        [
            ClearingObj.project.name,
            "my_release_name 0.0.1",
            "",
            "",
            "UNKNOWN",
            "UPLOADED",
            "",
            "",
            "",
        ]
    )


def test_upload_sources_continues_if_release_is_skiped(
    ClearingObj: Clearing, ReleaseObj: Release, monkeypatch
):
    release = ReleaseObj
    release.skip_upload = True
    ClearingObj.project.linked_releases = [release]
    logger_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.logger", logger_mock)
    ClearingObj.get_release_source = MagicMock()
    ClearingObj.upload_sources()
    ClearingObj.get_release_source.assert_not_called()
    assert (
        call("A total of 0 files have been uploaded for this project (0 still pending)")
        in logger_mock.info.mock_calls
    )


def test_upload_sources_logs_info_if_release_is_uploaded(
    ClearingObj: Clearing, ReleaseObj: Release, monkeypatch
):
    release = ReleaseObj
    ClearingObj.project.linked_releases = [release]
    logger_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.logger", logger_mock)
    ClearingObj.get_release_source = MagicMock(return_value=True)
    ClearingObj.upload_sources()
    ClearingObj.get_release_source.assert_called_once()
    assert (
        call("A total of 1 files have been uploaded for this project (0 still pending)")
        in logger_mock.info.mock_calls
    )


def test_upload_sources_logs_debug_if_release_already_exists(
    ClearingObj: Clearing, ReleaseObj: Release, monkeypatch
):
    release = ReleaseObj
    release.workflow_summary.upload_status = UploadStatus.EXISTS
    ClearingObj.project.linked_releases = [release]
    logger_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.logger", logger_mock)
    ClearingObj.get_release_source = MagicMock(return_value=False)
    ClearingObj.upload_sources()
    ClearingObj.get_release_source.assert_called_once()
    logger_mock.debug.assert_called_once()
    assert (
        call("A total of 0 files have been uploaded for this project (0 still pending)")
        in logger_mock.info.mock_calls
    )


def test_upload_sources_logs_error_if_release_has_multiple_sources(
    ClearingObj: Clearing, ReleaseObj: Release, monkeypatch
):
    release = ReleaseObj
    release.workflow_summary.upload_status = UploadStatus.MULTIPLE_SOURCE
    ClearingObj.project.linked_releases = [release]
    logger_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.logger", logger_mock)
    ClearingObj.get_release_source = MagicMock(return_value=False)
    ClearingObj.upload_sources()
    ClearingObj.get_release_source.assert_called_once()
    logger_mock.error.assert_called_once()
    assert (
        call("A total of 0 files have been uploaded for this project (0 still pending)")
        in logger_mock.info.mock_calls
    )


def test_upload_sources_sets_pending_status_correctly(
    ClearingObj: Clearing, ReleaseObj: Release, monkeypatch
):
    release = ReleaseObj
    ClearingObj.project.linked_releases = [release]
    ClearingObj.batch_size = 0
    logger_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.logger", logger_mock)
    ClearingObj.get_release_source = MagicMock()
    ClearingObj.upload_sources()
    ClearingObj.get_release_source.assert_not_called()
    assert release.workflow_summary.upload_status == UploadStatus.PENDING
    assert (
        call("A total of 0 files have been uploaded for this project (1 still pending)")
        in logger_mock.info.mock_calls
    )


def test_schedule_jobs_sets_unscheduled_status_correctly(
    ClearingObj: Clearing, ReleaseObj: Release, monkeypatch
):
    ClearingObj.foss.schedule_jobs = MagicMock(
        side_effect=FossologyApiError("Schedule Error", MagicMock())
    )
    logger_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.logger", logger_mock)
    assert not ClearingObj.schedule_jobs(
        MagicMock(), MagicMock(), ReleaseObj, "UnscheduledRelease", {}
    )
    logger_mock.error.assert_called_once()
    assert ReleaseObj.workflow_summary.upload_status == UploadStatus.UNSCHEDULED


def test_get_summary_and_upload_report_timeout_sets_error_and_returns(
    ClearingObj, ReleaseObj, monkeypatch
):
    monkeypatch.setattr(
        "fossology_workflow.clearing.wait_for_completion_expected_agents",
        lambda foss, upload, agents: False,
    )

    release = ReleaseObj
    release.fossology_upload = MagicMock(uploadname="upload_name", id="upload_id")
    release.workflow_summary = MagicMock()
    release.workflow_summary.report_status = None

    ClearingObj.upload_sw360_reports = MagicMock()

    ClearingObj.get_summary_and_upload_report(release)

    assert release.workflow_summary.report_status == ReportStatus.FOSSOLOGY_ERROR
    ClearingObj.upload_sw360_reports.assert_not_called()


def test_workflow_summary_handles_missing_fossology_status(
    ClearingObj, ReleaseObj, monkeypatch
):
    """Test that empty string is used when fossology_upload_summary is None"""
    release_no_status = ReleaseObj
    release_no_status.fossology_upload_summary = None
    csv_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.csv", csv_mock)
    ClearingObj.project = MagicMock(linked_releases=[release_no_status])
    ClearingObj.workflow_summary()

    row_call = csv_mock.writer().writerow.mock_calls[1]
    assert row_call == call(
        [
            ClearingObj.project.name,
            "my_release_name 0.0.1",
            "",
            "",
            "UNKNOWN",
            "",
            "",
            "",
            "",
        ]
    )


def test_workflow_summary_populates_fossology_status(
    ClearingObj, ReleaseObj, monkeypatch
):
    """Test that Fossology Status is correctly populated from upload summary"""
    release_with_status = ReleaseObj
    release_with_status.fossology_upload_summary = MagicMock(
        clearingStatus="Closed", filesToBeCleared="0"
    )
    csv_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.csv", csv_mock)
    ClearingObj.project = MagicMock(linked_releases=[release_with_status])
    ClearingObj.workflow_summary()

    row_call = csv_mock.writer().writerow.mock_calls[1]
    assert row_call == call(
        [
            ClearingObj.project.name,
            "my_release_name 0.0.1",
            "",
            "Closed",
            "UNKNOWN",
            "0",
            "VERY_SMALL",
            "",
            "",
        ]
    )


@pytest.mark.parametrize(
    "clearing_status", ["Open", "InProgress", "Closed", "Rejected"]
)
def test_workflow_summary_all_possible_fossology_status_values(
    ClearingObj, ReleaseObj, clearing_status, monkeypatch
):
    release = ReleaseObj
    release.fossology_upload_summary = MagicMock(
        clearingStatus=clearing_status, filesToBeCleared="50"
    )
    csv_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.csv", csv_mock)
    ClearingObj.project = MagicMock(linked_releases=[release])
    ClearingObj.workflow_summary()

    row_call = csv_mock.writer().writerow.mock_calls[1]
    assert row_call == call(
        [
            ClearingObj.project.name,
            "my_release_name 0.0.1",
            "",
            clearing_status,
            "UNKNOWN",
            "50",
            "VERY_SMALL",
            "",
            "",
        ]
    )
