# Copyright (c) Siemens 2020
# SPDX-License-Identifier: MIT

import datetime
import secrets
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fossology.enums import JobStatus
from fossology.obj import Folder, Job, ShowJob

from fossology_workflow.clearing import Clearing
from fossology_workflow.models import (
    Attachment,
    Release,
    ReportStatus,
    UploadStatus,
    WorkflowSummary,
)
from fossology_workflow.settings import Config


def pytest_sessionfinish():
    for csv_file in Path(".").glob("**/*.csv"):
        csv_file.unlink()


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("SW360_URL", "https://sw360.example.com")
    monkeypatch.setenv("SW360_TOKEN", "blah")
    monkeypatch.setenv("SW360_CR", "CR-42")
    monkeypatch.setenv("FOSSOLOGY_URL", "https://fossology.example.com")
    monkeypatch.setenv("FOSSOLOGY_TOKEN", "blah")
    monkeypatch.setenv("FOSSOLOGY_FOLDER", "2")
    monkeypatch.setenv("FOSSOLOGY_GROUP", "group")
    monkeypatch.setenv("UPLOADS_TO_FOSSOLOGY", "true")
    monkeypatch.setenv("REPORTS_TO_SW360", "true")
    monkeypatch.setenv("REUSE", "true")
    monkeypatch.setenv("UPLOAD_INITIAL_SCAN_REPORT", "true")
    monkeypatch.setenv("IGNORE_FLAG", "WF:ignore")
    monkeypatch.setenv("USE_SOURCE_FLAG", "WF:use_source")


@pytest.fixture()
def env_without_clearing_info(monkeypatch):
    monkeypatch.setenv("SW360_CR", "")
    monkeypatch.setenv("SW360_PROJECT", "")


@pytest.fixture
def ClearingObj(monkeypatch):
    foss_mock = MagicMock()
    foss_mock.list_uploads = MagicMock(return_value=([], None))
    monkeypatch.setattr("fossology_workflow.clearing.sw360.SW360", MagicMock())
    monkeypatch.setattr(
        "fossology_workflow.clearing.Fossology", MagicMock(return_value=foss_mock)
    )
    config = Config()
    clearing = Clearing(config)
    clearing.project = MagicMock(clearingRequestId="CR-007")
    clearing.project.data = {}

    return clearing


@pytest.fixture()
def LastReleases():
    return [
        {
            "id": "3765276512",
            "name": "Spring Core 4.3.4",
            "version": "4.3.4",
            "createdOn": "2024-12-01",
            "_links": {"self": {"href": "https://sw360.org/api/releases/3765276512"}},
        },
        {
            "id": "6868686868",
            "name": "Angular",
            "version": "2.3.1",
            "createdOn": "2024-12-01",
            "_links": {"self": {"href": "https://sw360.org/api/releases/6868686868"}},
        },
        {
            "id": "5656565656",
            "name": "Angular",
            "version": "2.3.1",
            "createdOn": "2024-12-01",
            "_links": {"self": {"href": "https://sw360.org/api/releases/5656565656"}},
        },
    ]


@pytest.fixture()
def ReleaseData():
    return {
        "id": "3765276512",
        "createdOn": "2024-12-01",
        "name": "Spring Core 4.3.4",
        "version": "4.3.4",
        "clearingState": "NEW",
    }


@pytest.fixture(scope="function")
def ReleaseObj():
    initial_summary = WorkflowSummary(
        upload_status=UploadStatus.UNKNOWN,
        report_status=ReportStatus.UNKNOWN,
        reuse_info="",
        url="",
    )
    release = Release(
        id="release_id",
        name="my_release_name",
        version="0.0.1",
        clearingState="",
        componentType="",
        workflow_summary=initial_summary,
        data={},
        skip_upload=False,
        fossology_upload=None,
        fossology_upload_summary=None,
    )
    yield release


@pytest.fixture()
def attachment():
    return {
        "filename": "attachment_name",
        "sha1": "da373e491d3863477568896089ee9457bc316783",
        "attachmentType": "SOME_TYPE",
        "_links": {"self": {"href": "https://sw360.org/api/attachments/1231231254"}},
    }


@pytest.fixture()
def AttachmentObj(attachment):
    return Attachment.from_json(attachment)


@pytest.fixture
def make_job():
    def _make_job(name: str) -> Job:
        return Job(
            secrets.randbelow(1000),
            name,
            datetime.datetime.today().isoformat(),
            secrets.randbelow(1000),
            secrets.randbelow(1000),
            secrets.randbelow(1000),
            datetime.datetime.today().isoformat(),
            JobStatus.COMPLETED,
        )

    return _make_job


@pytest.fixture
def make_job_queue():
    def _make_job_queue(type: str) -> dict:
        job_download = {"text": "Download text", "link": "Download link"}
        return {
            "jobQueueId": secrets.randbelow(1000),
            "jobQueueType": type,
            "startTime": datetime.datetime.today().isoformat(),
            "endTime": datetime.datetime.today().isoformat(),
            "status": "Completed",
            "itemsProcessed": secrets.randbelow(1000),
            "log": "log",
            "dependencies": [secrets.randbelow(1000), secrets.randbelow(1000)],
            "itemsPerSec": secrets.randbelow(1000),
            "canDoActions": False,
            "isInProgress": False,
            "isReady": True,
            "download": job_download,
        }

    return _make_job_queue


@pytest.fixture
def make_show_job(make_job_queue) -> ShowJob:
    def _make_show_job(job_id: int, job_name: str, upload_id: int) -> ShowJob:
        job_queue_test_agent = make_job_queue("test-agent")
        job_queue_mandatory_agent = make_job_queue("mandatory-agent")
        return ShowJob(
            job_id,
            job_name,
            [job_queue_test_agent, job_queue_mandatory_agent],
            upload_id,
        )

    return _make_show_job


@pytest.fixture()
def subfolder():
    return {
        "id": 42,
        "name": "release_name",
        "description": "A release subfolder",
        "parent": 1,
    }


@pytest.fixture()
def SubfolderObj(subfolder):
    return Folder.from_json(subfolder)
