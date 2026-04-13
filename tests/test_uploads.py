# Copyright (c) Siemens 2020
# SPDX-License-Identifier: MIT

from unittest.mock import MagicMock

from fossology.exceptions import FossologyApiError
from fossology.obj import Folder
from pytest import MonkeyPatch
from tenacity import RetryError

from fossology_workflow.clearing import Clearing
from fossology_workflow.models import Attachment, Release, UploadStatus


def test_upload_source_sets_upload_status_and_url(
    ClearingObj: Clearing,
    AttachmentObj: Attachment,
    monkeypatch: MonkeyPatch,
    ReleaseObj: Release,
):
    folder = MagicMock(id=42)
    upload = MagicMock()
    upload.hash.sha1 = "file_sha1"

    ClearingObj.foss.create_folder = MagicMock(return_value=folder)
    ClearingObj.foss.upload_file = MagicMock(return_value=upload)
    ClearingObj.source_already_exists = MagicMock(return_value=(None, False))
    logger_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.logger", logger_mock)
    monkeypatch.setattr("fossology_workflow.clearing.Path", MagicMock())
    monkeypatch.setattr(
        "fossology_workflow.clearing.get_filesha1", MagicMock(return_value="file_sha1")
    )
    release = ReleaseObj
    ClearingObj.upload_source(AttachmentObj, release)
    assert release.workflow_summary.upload_status == UploadStatus.UPLOADED
    assert release.fossology_upload == upload
    assert (
        release.workflow_summary.url
        == f"{ClearingObj.foss.host}/?mod=browse&folder={folder.id}"
    )
    assert len(logger_mock.info.mock_calls) == 2


def test_upload_source_returns_false_if_upload_failed(
    ClearingObj: Clearing,
    AttachmentObj: Attachment,
    ReleaseObj: Release,
    monkeypatch: MonkeyPatch,
):
    response = MagicMock()
    folder = MagicMock(id=42)
    ClearingObj.foss.create_folder = MagicMock(return_value=folder)
    ClearingObj.foss.upload_file = MagicMock(
        side_effect=FossologyApiError("Upload failed", response)
    )
    ClearingObj.source_already_exists = MagicMock(return_value=(None, False))
    logger_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.logger", logger_mock)
    monkeypatch.setattr("fossology_workflow.clearing.Path", MagicMock())
    ClearingObj.upload_source(AttachmentObj, ReleaseObj)
    assert not ReleaseObj.fossology_upload
    assert not ReleaseObj.workflow_summary.url
    assert ReleaseObj.workflow_summary.upload_status == UploadStatus.EMPTY
    logger_mock.error.assert_called_once()


def test_upload_source_returns_false_if_upload_took_too_long(
    ClearingObj: Clearing,
    AttachmentObj: Attachment,
    ReleaseObj: Release,
    monkeypatch: MonkeyPatch,
):
    response = MagicMock()
    folder = MagicMock(id=42)
    ClearingObj.foss.create_folder = MagicMock(return_value=folder)
    ClearingObj.foss.upload_file = MagicMock(side_effect=RetryError(response))
    ClearingObj.source_already_exists = MagicMock(return_value=(None, False))
    logger_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.logger", logger_mock)
    monkeypatch.setattr("fossology_workflow.clearing.Path", MagicMock())
    ClearingObj.upload_source(AttachmentObj, ReleaseObj)
    assert not ReleaseObj.fossology_upload
    assert not ReleaseObj.workflow_summary.url
    assert ReleaseObj.workflow_summary.upload_status == UploadStatus.EMPTY
    logger_mock.error.assert_called_once()


def test_upload_source_returns_false_if_upload_sha1_is_wrong(
    ClearingObj: Clearing,
    AttachmentObj: Attachment,
    ReleaseObj: Release,
    monkeypatch: MonkeyPatch,
):
    folder = MagicMock(id=42)
    hash_mock = MagicMock(sha1="file_sha1")
    ClearingObj.foss.create_folder = MagicMock(return_value=folder)
    ClearingObj.foss.upload_file = MagicMock(return_value=MagicMock(hash=hash_mock))
    ClearingObj.source_already_exists = MagicMock(return_value=(None, False))
    logger_mock = MagicMock()
    monkeypatch.setattr("fossology_workflow.clearing.logger", logger_mock)
    monkeypatch.setattr("fossology_workflow.clearing.Path", MagicMock())
    monkeypatch.setattr(
        "fossology_workflow.clearing.get_filesha1",
        MagicMock(return_value="another_sha1"),
    )
    ClearingObj.upload_source(AttachmentObj, ReleaseObj)
    assert not ReleaseObj.fossology_upload
    assert not ReleaseObj.workflow_summary.url
    assert ReleaseObj.workflow_summary.upload_status == UploadStatus.CORRUPT
    logger_mock.error.assert_called_once()


def test_source_already_exists_returns_none_if_upload_source_has_different_release_id(
    ClearingObj: Clearing,
):
    mocked_uploads = [
        MagicMock(
            uploadname="ExistingUpload",
            description=(
                "550115387bd74cd69d98a14bbacddde3, k8s.io/kube-openapi, 0.0.0-20220803164354-a70c9af30aea,"
                "clearingRequestId CR-800"
            ),
        )
    ]
    ClearingObj.foss.list_uploads = MagicMock(return_value=(mocked_uploads, 1))
    assert ClearingObj.source_already_exists(
        MagicMock(), "ExpectedUpload", "727904992dbf4520a7419cc20b8ef53e"
    ) == (None, False)


def test_create_subfolder_if_object_exists_returns_it(
    ClearingObj: Clearing, SubfolderObj: Folder
):
    ClearingObj.folders = [SubfolderObj]
    ClearingObj.clearing_folder.id = 1
    assert ClearingObj.create_subfolder("release_name") == SubfolderObj


def test_create_subfolder_calls_create_folder(
    ClearingObj: Clearing, SubfolderObj: Folder
):
    new_subfolder = MagicMock()
    ClearingObj.foss.create_folder = MagicMock(return_value=new_subfolder)
    ClearingObj.folders = [SubfolderObj]
    assert ClearingObj.create_subfolder("another_release_name") == new_subfolder
    assert new_subfolder in ClearingObj.folders


def test_source_already_exists_returns_completed_jobs_status(
    ClearingObj: Clearing,
    monkeypatch: MonkeyPatch,
):
    mocked_uploads = [MagicMock(uploadname="ExpectedUpload")]
    mocked_release_id = MagicMock(return_value=1)
    mocked_agents_completed = MagicMock(return_value=True)
    monkeypatch.setattr(
        "fossology_workflow.clearing.get_upload_release_id", mocked_release_id
    )
    monkeypatch.setattr(
        "fossology_workflow.clearing.agents_started_or_completed",
        mocked_agents_completed,
    )
    ClearingObj.mandatory_agents = ["mandatory-agent"]
    ClearingObj.foss.list_uploads = MagicMock(return_value=(mocked_uploads, 1))
    assert ClearingObj.source_already_exists(MagicMock(), "ExpectedUpload", 1) == (
        mocked_uploads[0],
        True,
    )
