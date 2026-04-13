# Copyright (c) Siemens 2020
# SPDX-License-Identifier: MIT

from unittest.mock import MagicMock, call

import pytest

from fossology_workflow.clearing import Clearing
from fossology_workflow.models import Attachment, Release, UploadStatus
from fossology_workflow.settings import Config


@pytest.fixture
def Folder():
    return MagicMock()


@pytest.fixture
def Upload():
    return MagicMock()


def test_get_reuse_no_uploads(
    ClearingObj: Clearing, Folder: MagicMock, Upload: MagicMock
):
    assert not ClearingObj.get_reuse_upload(Folder, Upload)
    assert (
        call(folder=Folder, all_pages=True, group=ClearingObj.group)
        in ClearingObj.foss.list_uploads.mock_calls
    )


def test_get_reuse_no_clearings(
    ClearingObj: Clearing, Folder: MagicMock, Upload: MagicMock
):
    upload1 = Upload()
    upload2 = Upload()

    def upload_summary(foss, upload):
        if upload == upload1:
            summary = MagicMock()
            summary.clearingStatus = "InProgress"
            return summary
        else:
            summary = MagicMock()
            summary.clearingStatus = "Rejected"
            return summary

    ClearingObj.foss.list_uploads = MagicMock(return_value=([upload1, upload2], None))
    ClearingObj.foss.upload_summary = MagicMock(side_effect=upload_summary)
    assert not ClearingObj.get_reuse_upload(Folder, Upload)
    assert (
        call(folder=Folder, all_pages=True, group=ClearingObj.group)
        in ClearingObj.foss.list_uploads.mock_calls
    )
    assert len(ClearingObj.foss.upload_summary.mock_calls) == 2


def test_get_reuse_choses_last_upload(
    ClearingObj: Clearing, Folder: MagicMock, Upload: MagicMock
):
    upload1 = Upload()
    upload1.uploaddate = "2020-07-27 07:18:01.87237+00"
    upload2 = Upload()
    upload2.uploaddate = "2021-07-27 07:18:01.87237+00"

    def upload_summary(foss, upload):
        summary = MagicMock()
        summary.clearingStatus = "Closed"
        return summary

    ClearingObj.foss.list_uploads = MagicMock(return_value=([upload1, upload2], None))
    ClearingObj.foss.upload_summary = MagicMock(side_effect=upload_summary)
    assert ClearingObj.get_reuse_upload(Folder, Upload) == upload2
    assert (
        call(folder=Folder, all_pages=True, group=ClearingObj.group)
        in ClearingObj.foss.list_uploads.mock_calls
    )
    assert len(ClearingObj.foss.upload_summary.mock_calls) == 2


def test_upload_source_reuses_last_upload(
    monkeypatch: pytest.MonkeyPatch,
    AttachmentObj: Attachment,
    ClearingObj: Clearing,
    Folder: MagicMock,
    Upload: MagicMock,
    ReleaseObj: Release,
):
    upload_folder = Folder()
    new_upload = Upload()
    new_upload.hash.sha1 = "file_sha1"
    existing_upload1 = Upload()
    existing_upload1.uploaddate = "2020-07-27 07:18:01.87237+00"
    existing_upload2 = Upload()
    existing_upload2.uploaddate = "2021-07-27 07:18:01.87237+00"
    existing_upload2.id = 42

    def upload_summary(foss, upload):
        summary = MagicMock()
        summary.clearingStatus = "Closed"
        return summary

    ClearingObj.foss.create_folder = MagicMock(return_value=upload_folder)
    ClearingObj.foss.upload_file = MagicMock(return_value=new_upload)
    ClearingObj.foss.list_uploads = MagicMock(
        return_value=([existing_upload1, existing_upload2], None)
    )
    ClearingObj.foss.upload_summary = MagicMock(side_effect=upload_summary)
    monkeypatch.setattr(
        "fossology_workflow.clearing.get_filesha1", MagicMock(return_value="file_sha1")
    )
    monkeypatch.setattr("fossology_workflow.clearing.Path", MagicMock())
    ClearingObj.upload_source(AttachmentObj, ReleaseObj)
    verify_job_spec = Config().DEFAULT_JOB_SPEC
    verify_job_spec["reuse"]["reuse_upload"] = existing_upload2.id
    assert (
        call(upload_folder, existing_upload2, verify_job_spec, group=ClearingObj.group)
        in ClearingObj.foss.schedule_jobs.mock_calls
    )


def test_upload_source_does_not_inherit_reuseid_from_last_upload(
    monkeypatch: pytest.MonkeyPatch,
    AttachmentObj: Attachment,
    ClearingObj: Clearing,
    Folder: MagicMock,
    Upload: MagicMock,
    ReleaseObj: Release,
):
    upload_folder = Folder()
    new_upload = Upload()
    new_upload.hash.sha1 = "file_sha1"
    existing_upload = Upload()
    existing_upload.id = 42
    existing_upload.uploaddate = "2020-07-27 07:18:01.87237+00"

    def upload_summary(foss, upload):
        summary = MagicMock()
        summary.clearingStatus = "Closed"
        return summary

    ClearingObj.foss.create_folder = MagicMock(return_value=upload_folder)
    ClearingObj.foss.upload_file = MagicMock(return_value=new_upload)
    ClearingObj.foss.list_uploads = MagicMock(return_value=([existing_upload], None))
    ClearingObj.foss.upload_summary = MagicMock(side_effect=upload_summary)
    monkeypatch.setattr(
        "fossology_workflow.clearing.get_filesha1", MagicMock(return_value="file_sha1")
    )
    monkeypatch.setattr("fossology_workflow.clearing.Path", MagicMock())
    verify_job_spec = Config().DEFAULT_JOB_SPEC
    verify_job_spec["reuse"]["reuse_upload"] = existing_upload.id
    ClearingObj.upload_source(AttachmentObj, ReleaseObj)
    assert (
        call(upload_folder, new_upload, verify_job_spec, group=ClearingObj.group)
        in ClearingObj.foss.schedule_jobs.mock_calls
    )
    ClearingObj.foss.list_uploads = MagicMock(return_value=([], None))
    ClearingObj.upload_source(AttachmentObj, ReleaseObj)
    assert Config().DEFAULT_JOB_SPEC["reuse"]["reuse_upload"] == 0
    # If REUSE is set to true, job won't be scheduled if there is no reuse_upload_id
    assert (
        call(
            upload_folder,
            new_upload,
            Config().DEFAULT_JOB_SPEC,
            group=ClearingObj.group,
        )
        not in ClearingObj.foss.schedule_jobs.mock_calls
    )


def test_verify_reuse_is_not_performed_if_set_to_false(
    monkeypatch: pytest.MonkeyPatch,
    AttachmentObj: Attachment,
    ClearingObj: Clearing,
    Folder: MagicMock,
    Upload: MagicMock,
    ReleaseObj: Release,
):
    upload_folder = Folder()
    new_upload = Upload()
    new_upload.hash.sha1 = "file_sha1"
    existing_upload = Upload()
    existing_upload.id = 42
    existing_upload.uploaddate = "2020-07-27 07:18:01.87237+00"

    def upload_summary(foss, upload):
        summary = MagicMock()
        summary.clearingStatus = "Closed"
        return summary

    ClearingObj.reuse = False
    ClearingObj.foss.create_folder = MagicMock(return_value=upload_folder)
    ClearingObj.foss.upload_file = MagicMock(return_value=new_upload)
    ClearingObj.foss.list_uploads = MagicMock(return_value=([existing_upload], None))
    ClearingObj.foss.upload_summary = MagicMock(side_effect=upload_summary)
    monkeypatch.setattr(
        "fossology_workflow.clearing.get_filesha1", MagicMock(return_value="file_sha1")
    )
    monkeypatch.setattr("fossology_workflow.clearing.Path", MagicMock())
    ClearingObj.upload_source(
        AttachmentObj,
        ReleaseObj,
    )
    assert (
        call(
            upload_folder,
            new_upload,
            Config().DEFAULT_JOB_SPEC,
            group=ClearingObj.group,
        )
        in ClearingObj.foss.schedule_jobs.mock_calls
    )


def test_reuse_info_returned_by_upload_source(
    monkeypatch: pytest.MonkeyPatch,
    AttachmentObj: Attachment,
    ClearingObj: Clearing,
    Folder: MagicMock,
    Upload: MagicMock,
    ReleaseObj: Release,
):
    upload_folder = Folder()
    new_upload = Upload()
    new_upload.hash.sha1 = "file_sha1"
    existing_upload = Upload()
    existing_upload.id = 42
    existing_upload.uploadname = "Previous Upload"
    existing_upload.uploaddate = "2020-07-27 07:18:01.87237+00"

    def upload_summary(foss, upload):
        summary = MagicMock()
        summary.clearingStatus = "Closed"
        return summary

    ClearingObj.reuse = False
    ClearingObj.foss.create_folder = MagicMock(return_value=upload_folder)
    ClearingObj.foss.upload_file = MagicMock(return_value=new_upload)
    ClearingObj.foss.list_uploads = MagicMock(return_value=([existing_upload], None))
    ClearingObj.foss.upload_summary = MagicMock(side_effect=upload_summary)
    monkeypatch.setattr(
        "fossology_workflow.clearing.get_filesha1", MagicMock(return_value="file_sha1")
    )
    monkeypatch.setattr("fossology_workflow.clearing.Path", MagicMock())
    ClearingObj.upload_source(
        AttachmentObj,
        ReleaseObj,
    )
    assert (
        ReleaseObj.workflow_summary.reuse_info
        == "Previous Upload (from 2020-07-27 07:18:01.87237+00)"
    )


def test_upload_source_reuses_last_upload_when_reuse_is_switched(
    monkeypatch: pytest.MonkeyPatch,
    AttachmentObj: Attachment,
    ClearingObj: Clearing,
    Folder: MagicMock,
    Upload: MagicMock,
    ReleaseObj: Release,
):
    upload_folder = Folder()
    new_upload = Upload()
    new_upload.hash.sha1 = "file_sha1"
    existing_upload = Upload()
    existing_upload.id = 42
    existing_upload.uploadname = "Previous Upload"
    existing_upload.uploaddate = "2020-07-27 07:18:01.87237+00"

    def upload_summary(foss, upload):
        summary = MagicMock()
        summary.clearingStatus = "Closed"
        return summary

    ClearingObj.reuse = False
    ClearingObj.foss.create_folder = MagicMock(return_value=upload_folder)
    ClearingObj.foss.upload_file = MagicMock(return_value=new_upload)
    ClearingObj.foss.list_uploads = MagicMock(return_value=([existing_upload], None))
    ClearingObj.foss.upload_summary = MagicMock(side_effect=upload_summary)
    monkeypatch.setattr(
        "fossology_workflow.clearing.get_filesha1", MagicMock(return_value="file_sha1")
    )
    monkeypatch.setattr("fossology_workflow.clearing.Path", MagicMock())
    ClearingObj.upload_source(
        AttachmentObj,
        ReleaseObj,
    )
    assert (
        ReleaseObj.workflow_summary.reuse_info
        == "Previous Upload (from 2020-07-27 07:18:01.87237+00)"
    )

    ClearingObj.reuse = True
    ClearingObj.upload_source(
        AttachmentObj,
        ReleaseObj,
    )
    verify_job_spec = Config().DEFAULT_JOB_SPEC
    verify_job_spec["reuse"]["reuse_upload"] = existing_upload.id
    assert (
        call(upload_folder, existing_upload, verify_job_spec, group=ClearingObj.group)
        in ClearingObj.foss.schedule_jobs.mock_calls
    )


def test_upload_source_returns_false_if_uploads_to_fossology_is_set_to_false(
    AttachmentObj: Attachment,
    ClearingObj: Clearing,
    Folder: MagicMock,
    Upload: MagicMock,
    ReleaseObj: Release,
):
    upload_folder = Folder()
    existing_upload = Upload()
    existing_upload.id = 42
    existing_upload.uploadname = "another_source_file"

    ClearingObj.uploads_to_fossology = False
    ClearingObj.foss.create_folder = MagicMock(return_value=upload_folder)
    ClearingObj.foss.list_uploads = MagicMock(return_value=([existing_upload], None))
    assert not ClearingObj.upload_source(AttachmentObj, ReleaseObj)
    assert ReleaseObj.workflow_summary.upload_status == UploadStatus.DO_NOT_UPLOAD
