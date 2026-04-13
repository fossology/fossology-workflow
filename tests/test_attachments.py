# Copyright (c) Siemens 2020
# SPDX-License-Identifier: MIT

from unittest.mock import MagicMock

import pytest
import sw360
from pytest import MonkeyPatch

from fossology_workflow.clearing import Clearing
from fossology_workflow.helpers import (
    get_release_attachments,
    get_source_attachment,
    get_use_source,
    initial_scan_available,
)
from fossology_workflow.models import Attachment, Release, UploadStatus, WorkflowSummary
from fossology_workflow.settings import Config


def test_get_release_attachments(attachment: dict, ReleaseObj: Release):
    release = ReleaseObj
    release.data = {"_embedded": {"sw360:attachments": [attachment]}}
    attachments = get_release_attachments(release)
    assert isinstance(attachments[0], Attachment)


def test_get_release_attachments_returns_none_if_no_attachments(ReleaseObj: Release):
    release = ReleaseObj
    release.data = {}
    assert not get_release_attachments(release)
    assert release.workflow_summary.upload_status == UploadStatus.NO_SOURCE


def test_get_release_attachments_with_default_force_reclearing_flag(
    attachment: dict, ReleaseObj: Release, monkeypatch: MonkeyPatch
):
    monkeypatch.delenv("FORCE_RECLEARING_FLAG", raising=False)
    attachment["attachmentType"] = "CLEARING_REPORT"
    release = ReleaseObj
    release.data = {
        "_embedded": {"sw360:attachments": [attachment]},
        "additionalData": {"WF:force_reclearing": ""},
    }

    attachments = get_release_attachments(release)
    assert isinstance(attachments[0], Attachment)
    assert release.workflow_summary.upload_status == UploadStatus.UNKNOWN


@pytest.mark.parametrize(
    "attachment_type",
    ["CLEARING_REPORT", "COMPONENT_LICENSE_INFO_XML", "INITIAL_SCAN_REPORT"],
)
def test_get_release_attachments_returns_none_if_report_already_exists(
    attachment: dict, attachment_type: str, ReleaseObj: Release
):
    attachment["attachmentType"] = attachment_type
    release_info = ReleaseObj
    release_info.data = {"_embedded": {"sw360:attachments": [attachment]}}
    if attachment_type != "INITIAL_SCAN_REPORT":
        assert not get_release_attachments(release_info)
        assert release_info.workflow_summary.upload_status == UploadStatus.CLEARED
    else:
        attachments = get_release_attachments(release_info)
        assert filter(lambda x: x.attachmentType == "INITIAL_SCAN_REPORT", attachments)


@pytest.mark.parametrize(
    "attachment_type",
    ["SOURCE_ZIP", "SOURCE_TAR", "SRS", "OTHER_TYPE"],
)
def test_get_source_returns_filtered_attachments_with_source(
    attachment: dict, attachment_type: str, ReleaseObj: Release
):
    attachment1 = Attachment.from_json(attachment)
    attachment1.attachmentType = attachment_type
    attachment2 = Attachment.from_json(attachment)
    attachments = [attachment1, attachment2]
    release = ReleaseObj
    if attachment_type == "OTHER_TYPE":
        assert not get_source_attachment(attachments, release)
        assert release.workflow_summary.upload_status == UploadStatus.NO_SOURCE
    else:
        source = get_source_attachment(attachments, release)
        assert source.attachmentType == attachment_type


def test_get_source_returns_none_if_several_sources_are_available(
    attachment: dict, ReleaseObj: Release
):
    attachment1 = Attachment.from_json(attachment)
    attachment1.attachmentType = "SOURCE"
    attachment2 = Attachment.from_json(attachment)
    attachment2.attachmentType = "SOURCE"
    attachments = [attachment1, attachment2]
    release = ReleaseObj
    assert not get_source_attachment(attachments, release)
    assert release.workflow_summary.upload_status == UploadStatus.MULTIPLE_SOURCE


def test_get_source_from_data_returns_filtered_attachments_with_required_source(
    attachment: dict, ReleaseObj: Release
):
    attachment1 = Attachment.from_json(attachment)
    attachment1.filename = "wanted"
    attachment2 = Attachment.from_json(attachment)
    attachments = [attachment1, attachment2]
    release = ReleaseObj
    assert not get_use_source("filename", attachments, release)
    assert release.workflow_summary.upload_status == UploadStatus.NO_SOURCE_SPEC

    source = get_use_source("wanted", attachments, release)
    assert source.filename == "wanted"


def test_get_source_from_data_with_several_source_returns_none(
    attachment: dict, ReleaseObj: Release
):
    attachment1 = Attachment.from_json(attachment)
    attachment1.filename = "wanted"
    attachment2 = Attachment.from_json(attachment)
    attachment2.filename = "wanted"
    attachment3 = Attachment.from_json(attachment)
    attachments = [attachment1, attachment2, attachment3]
    release = ReleaseObj
    assert not get_use_source("wanted", attachments, release)
    assert release.workflow_summary.upload_status == UploadStatus.MULTIPLE_SOURCE_SPEC


def test_get_source_attachment_with_use_source_flag_returns_expected_source(
    attachment: dict, ReleaseObj: Release
):
    attachment1 = Attachment.from_json(attachment)
    attachment1.filename = "not_wanted"
    attachment1.attachmentType = "SOURCE"
    attachment2 = Attachment.from_json(attachment)
    attachment2.filename = "wanted"
    attachment2.attachmentType = "SOURCE"
    attachment3 = Attachment.from_json(attachment)
    attachments = [attachment1, attachment2, attachment3]
    attachment3.attachmentType = "SOURCE"
    release = ReleaseObj
    release.data = {"additionalData": {"WF:use_source": "wanted"}}
    assert get_source_attachment(attachments, release) == attachment2
    assert release.workflow_summary.upload_status == UploadStatus.UNKNOWN


def test_get_source_attachment_with_default_use_source_flag_returns_expected_source(
    attachment: dict, ReleaseObj: Release, monkeypatch: MonkeyPatch
):
    monkeypatch.delenv("USE_SOURCE_FLAG", raising=False)

    attachment1 = Attachment.from_json(attachment)
    attachment1.filename = "not_wanted"
    attachment1.attachmentType = "SOURCE"
    attachment2 = Attachment.from_json(attachment)
    attachment2.filename = "wanted"
    attachment2.attachmentType = "SOURCE"
    attachment3 = Attachment.from_json(attachment)
    attachment3.attachmentType = "SOURCE"
    attachments = [attachment1, attachment2, attachment3]

    release = ReleaseObj
    release.data = {"additionalData": {"WF:use_source": "wanted"}}

    assert get_source_attachment(attachments, release) == attachment2
    assert release.workflow_summary.upload_status == UploadStatus.UNKNOWN


def test_upload_source_handles_download_failure(
    ClearingObj: Clearing,
    ReleaseObj: Release,
    AttachmentObj: Attachment,
    monkeypatch: MonkeyPatch,
):
    release = ReleaseObj
    release.id = "release-abc-123"
    release.name = "TestComponent"
    release.version = "1.0"

    attachment = AttachmentObj
    attachment.filename = "source-code.zip"
    attachment._links["self"]["href"] = "/api/attachments/attachment-def-456"

    monkeypatch.setattr(
        "fossology_workflow.clearing.normalize_release_name", MagicMock()
    )
    monkeypatch.setattr(ClearingObj, "create_subfolder", MagicMock())
    monkeypatch.setattr(
        ClearingObj, "source_already_exists", MagicMock(return_value=(None, None))
    )
    monkeypatch.setattr(
        "fossology_workflow.clearing.extract_resource_id",
        MagicMock(return_value="attachment-def-456"),
    )
    mock_logger_error = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.logger.error", mock_logger_error)

    mock_response = MagicMock()
    mock_response.text = "{}"
    mock_response.__str__.return_value = "HTTP 404 Not Found"
    mock_download = MagicMock(side_effect=sw360.SW360Error(response=mock_response))

    monkeypatch.setattr(ClearingObj.sw360, "download_release_attachment", mock_download)
    ClearingObj.uploads_to_fossology = True

    result = ClearingObj.upload_source(attachment, release)

    assert not result
    assert release.workflow_summary.upload_status == UploadStatus.NO_SOURCE_SPEC

    mock_download.assert_called_once_with(
        "source-code.zip", "release-abc-123", "attachment-def-456"
    )

    mock_logger_error.assert_called_once()
    logged_message = mock_logger_error.call_args[0][0]
    assert "Failed to download attachment" in logged_message
    assert "source-code.zip for release TestComponent (1.0)" in logged_message
    assert "HTTP 404 Not Found" in logged_message


def test_initial_scan_report_available_returns_expected_value(
    AttachmentObj: Attachment,
):
    assert not initial_scan_available([AttachmentObj])
    AttachmentObj.attachmentType = "INITIAL_SCAN_REPORT"
    assert initial_scan_available([AttachmentObj])


def test_get_release_source(
    monkeypatch: MonkeyPatch, attachment: dict, ReleaseObj: Release
):
    monkeypatch.setattr(
        "fossology_workflow.clearing.get_filesha1",
        MagicMock(return_value="da373e491d3863477568896089ee9457bc316783"),
    )
    monkeypatch.setattr("fossology_workflow.clearing.Path", MagicMock())
    monkeypatch.setattr("fossology_workflow.clearing.sw360.SW360", MagicMock())
    monkeypatch.setattr("fossology_workflow.clearing.Fossology", MagicMock())
    config = Config()
    clearing = Clearing(config)
    clearing.project = MagicMock(clearingRequestId="abcd-request")

    upload = MagicMock()
    upload.hash.sha1 = "da373e491d3863477568896089ee9457bc316783"
    clearing.foss.upload_file = MagicMock(return_value=upload)
    clearing.get_reuse_upload = MagicMock()
    attachment["attachmentType"] = "SOURCE"
    release = ReleaseObj
    release.id = "abcd"
    release.name = "release-abcd"
    release.version = "1.0.0"
    release.data = {
        "name": "MyRelease",
        "version": "1.0.0",
        "_embedded": {"sw360:attachments": [attachment]},
    }
    release.workflow_summary = WorkflowSummary()
    clearing.get_release_source(release)


def test_upload_attachment_sends_file_to_sw360(
    ClearingObj: Clearing, ReleaseObj: Release
):
    release = ReleaseObj
    report_content = bytes("This is a clearing report", "UTF-8")
    ClearingObj.sw360.upload_release_attachment = MagicMock()
    ClearingObj.upload_attachment(
        report_content, "my_clearing_report.xml", "COMPONENT_LICENSE_INFO_XML", release
    )
    ClearingObj.sw360.upload_release_attachment.assert_called_once()
