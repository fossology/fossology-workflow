# Copyright (c) Siemens 2020
# SPDX-License-Identifier: MIT

from typing import Callable
from unittest.mock import MagicMock

from pytest import MonkeyPatch

from fossology_workflow.clearing import Clearing
from fossology_workflow.helpers import (
    agents_started_or_completed,
    wait_for_completion_expected_agents,
)


def test_agents_started_or_completed_returns_true_if_mandatory_jobs_are_completed(
    ClearingObj: Clearing,
    make_show_job: Callable,
    monkeypatch: MonkeyPatch,
):
    mocked_upload = MagicMock(uploadname="ExpectedUpload")
    mocked_show_job = make_show_job(1, "ExpectedUpload", 1)
    mocked_time = MagicMock()
    monkeypatch.setattr("fossology_workflow.helpers.time", mocked_time)
    ClearingObj.foss.jobs_history = MagicMock(return_value=[mocked_show_job])
    assert agents_started_or_completed(
        ClearingObj.foss, mocked_upload, ["mandatory-agent"]
    )


def test_agents_started_or_completed_returns_true_if_mandatory_jobs_are_queued(
    ClearingObj: Clearing,
    make_show_job: Callable,
    monkeypatch: MonkeyPatch,
):
    mocked_upload = MagicMock(uploadname="ExpectedUpload")
    mocked_show_job = make_show_job(1, "ExpectedUpload", 1)
    mocked_show_job.jobQueue[1].status = "Queued"
    mocked_time = MagicMock()
    monkeypatch.setattr("fossology_workflow.helpers.time", mocked_time)
    ClearingObj.foss.jobs_history = MagicMock(return_value=[mocked_show_job])
    assert agents_started_or_completed(
        ClearingObj.foss, mocked_upload, ["mandatory-agent"]
    )


def test_agents_started_or_completed_returns_true_if_mandatory_jobs_are_started(
    ClearingObj: Clearing,
    make_show_job: Callable,
    monkeypatch: MonkeyPatch,
):
    mocked_upload = MagicMock(uploadname="ExpectedUpload")
    mocked_show_job = make_show_job(1, "ExpectedUpload", 1)
    mocked_show_job.jobQueue[1].status = "Started"
    mocked_time = MagicMock()
    monkeypatch.setattr("fossology_workflow.helpers.time", mocked_time)
    ClearingObj.foss.jobs_history = MagicMock(return_value=[mocked_show_job])
    assert agents_started_or_completed(
        ClearingObj.foss, mocked_upload, ["mandatory-agent"]
    )


def test_agents_started_or_completed_returns_false_if_mandatory_agents_are_failed(
    ClearingObj: Clearing,
    make_show_job: Callable,
    monkeypatch: MonkeyPatch,
):
    mocked_upload = MagicMock(uploadname="ExpectedUpload")
    mocked_show_job = make_show_job(1, "ExpectedUpload", 1)
    mocked_show_job.jobQueue[1].status = "Failed"
    mocked_time = MagicMock()
    monkeypatch.setattr("fossology_workflow.helpers.time", mocked_time)
    ClearingObj.foss.jobs_history = MagicMock(return_value=[mocked_show_job])
    assert not agents_started_or_completed(
        ClearingObj.foss, mocked_upload, ["mandatory-agent"]
    )


def test_agents_started_or_completed_returns_false_if_mandatory_were_not_scheduled(
    ClearingObj: Clearing,
    make_show_job: Callable,
    monkeypatch: MonkeyPatch,
):
    mocked_upload = MagicMock(uploadname="ExpectedUpload")
    mocked_show_job = make_show_job(1, "ExpectedUpload", 1)
    mocked_time = MagicMock()
    monkeypatch.setattr("fossology_workflow.helpers.time", mocked_time)
    ClearingObj.foss.jobs_history = MagicMock(return_value=[mocked_show_job])
    assert not agents_started_or_completed(
        ClearingObj.foss, mocked_upload, ["unscheduled-agent"]
    )


def test_wait_completion_expected_jobs_waits_until_all_jobs_are_finished(
    ClearingObj: Clearing,
    make_show_job: Callable,
    monkeypatch: MonkeyPatch,
):
    mocked_upload = MagicMock(uploadname="ExpectedUpload")
    mocked_show_job_in_progress = make_show_job(1, "ExpectedUpload", 1)
    mocked_show_job_in_progress.jobQueue[1].isInProgress = True
    mocked_show_job_terminated = make_show_job(1, "ExpectedUpload", 1)

    mocked_sleep = MagicMock()
    mocked_logger = MagicMock()

    monkeypatch.setattr("fossology_workflow.helpers.time.sleep", mocked_sleep)
    monkeypatch.setattr("fossology_workflow.helpers.logger", mocked_logger)

    ClearingObj.mandatory_agents = ["mandatory-agent"]

    ClearingObj.foss.jobs_history = MagicMock(
        side_effect=[[mocked_show_job_in_progress], [mocked_show_job_terminated]]
    )

    wait_for_completion_expected_agents(
        ClearingObj.foss, mocked_upload, ["mandatory-agent"]
    )

    mocked_sleep.assert_called()


def test_wait_completion_expected_jobs_does_not_sleep_if_all_expected_jobs_are_finished(
    ClearingObj: Clearing,
    make_show_job: Callable,
    monkeypatch: MonkeyPatch,
):
    mocked_upload = MagicMock(uploadname="ExpectedUpload")
    mocked_show_job = make_show_job(1, "ExpectedUpload", 1)
    mocked_logger = MagicMock()
    mocked_timer = MagicMock()
    monkeypatch.setattr("fossology_workflow.helpers.time.sleep", mocked_timer)
    monkeypatch.setattr("fossology_workflow.helpers.logger", mocked_logger)

    ClearingObj.mandatory_agents = ["mandatory-agent"]
    ClearingObj.foss.jobs_history = MagicMock(return_value=[mocked_show_job])

    wait_for_completion_expected_agents(
        ClearingObj.foss, mocked_upload, ["mandatory-agent"]
    )

    mocked_timer.assert_not_called()
    mocked_logger.debug.assert_not_called()


def test_wait_for_completion_expected_agents_times_out_immediately(monkeypatch):
    agent = MagicMock(jobQueueType="mandatory-agent", isInProgress=True)
    job = MagicMock(jobQueue=[agent])
    foss = MagicMock()
    foss.jobs_history = MagicMock(return_value=[job])
    upload = MagicMock(uploadname="UploadX")

    fake_logger = MagicMock()
    monkeypatch.setattr("fossology_workflow.helpers.logger", fake_logger)

    result = wait_for_completion_expected_agents(
        foss,
        upload,
        mandatory_agents=["mandatory-agent"],
        timeout=0,
    )

    assert result is False
    fake_logger.warning.assert_called_once_with(
        "Timeout reached while waiting for agents to complete for upload UploadX"
    )
    foss.jobs_history.assert_called_once_with(upload=upload)


def test_wait_for_completion_expected_agents_returns_true_if_no_agents_in_progress():
    agent = MagicMock(jobQueueType="other-agent", isInProgress=True)
    job = MagicMock(jobQueue=[agent])
    foss = MagicMock()
    foss.jobs_history = MagicMock(return_value=[job])
    upload = MagicMock(uploadname="UploadY")

    result = wait_for_completion_expected_agents(
        foss,
        upload,
        mandatory_agents=["mandatory-agent"],
        timeout=0,
    )

    assert result is True
    foss.jobs_history.assert_called_once_with(upload=upload)
