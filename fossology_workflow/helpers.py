# Copyright (c) Siemens 2020
# SPDX-License-Identifier: MIT

import hashlib
import logging
import os
import re
import time  # noqa: F401
import unicodedata
from typing import List, Optional

from fossology import Fossology
from fossology.obj import Upload
from tenacity import RetryError, retry, retry_if_result, stop_after_delay, wait_fixed

from fossology_workflow.models import (
    Attachment,
    ClearingComplexity,
    EffortEstimation,
    Release,
    UploadStatus,
)

logger = logging.getLogger(__name__)

DEFAULT_USE_SOURCE_FLAG = "WF:use_source"
DEFAULT_FORCE_RECLEARING_FLAG = "WF:force_reclearing"


def strtobool(val: str) -> int:
    """Convert a string representation of truth to true (1) or false (0).
    True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
    are 'n', 'no', 'f', 'false', 'off', and '0'.  Raises ValueError if
    'val' is anything else.
    """
    val = val.lower()
    if val in ("y", "yes", "t", "true", "on", "1"):
        return 1
    elif val in ("n", "no", "f", "false", "off", "0"):
        return 0
    else:
        raise ValueError("invalid truth value %r" % (val,))


def normalize_release_name(name: str) -> str:
    # Handle special case with delete control character U+\007F
    # e.g. in release name 'django-extensions\x7F'
    delete = re.compile("\x7f")
    name = delete.sub("", name)
    # Make sure only utf-8 characters are used for release folders
    # https://docs.python.org/3/library/unicodedata.html#unicodedata.normalize
    nkfd_form = unicodedata.normalize("NFKD", name)
    return "".join([c for c in nkfd_form if not unicodedata.combining(c)])


def normalize_report_name(name: str) -> str:
    # Reports might contain timestamp in the file name with the character ":"
    # Replace this character with "_"
    return name.replace(":", "_")


def initial_scan_available(attachments: list[Attachment]):
    return list(
        filter(lambda x: x.attachmentType == "INITIAL_SCAN_REPORT", attachments)
    )


def get_filesha1(filepath: str) -> str:
    with open(filepath, "rb") as f:
        file_hash = hashlib.sha1()
        while chunk := f.read(8192):
            file_hash.update(chunk)
    return file_hash.hexdigest().upper()


def extract_resource_id(resource_url: str) -> str:
    return resource_url.split("/")[-1]


def get_use_source(
    use_source: str, attachments: List[Attachment], release: Release
) -> Optional[Attachment]:
    source = list(filter(lambda x: x.filename == use_source, attachments))
    if not source:
        release.workflow_summary.upload_status = UploadStatus.NO_SOURCE_SPEC
        return None

    if 1 < len(source):
        release.workflow_summary.upload_status = UploadStatus.MULTIPLE_SOURCE_SPEC
        return None

    return source[0]


def get_source_attachment(
    attachments: List[Attachment], release: Release
) -> Optional[Attachment]:
    """Only attachments from type SOURCE_* or SRS are downloaded"""
    source_attachments = list(
        filter(
            lambda x: x.attachmentType == "SRS" or re.match("SOURCE", x.attachmentType),
            attachments,
        )
    )
    additional_data = release.data.get("additionalData", {})
    use_source_flag = os.getenv("USE_SOURCE_FLAG", default=DEFAULT_USE_SOURCE_FLAG)
    if use_source := additional_data.get(use_source_flag, ""):
        return get_use_source(use_source, source_attachments, release)

    if 1 < len(source_attachments):
        release.workflow_summary.upload_status = UploadStatus.MULTIPLE_SOURCE
        return None

    if not source_attachments:
        release.workflow_summary.upload_status = UploadStatus.NO_SOURCE
        return None

    return source_attachments[0]


def get_release_attachments(release: Release) -> Optional[list]:
    try:
        raw_attachments = release.data["_embedded"]["sw360:attachments"]
    except KeyError:
        release.workflow_summary.upload_status = UploadStatus.NO_SOURCE
        return None

    normalized_attachments = []
    for item in raw_attachments:
        if isinstance(item, list):
            normalized_attachments.extend(item)
        else:
            normalized_attachments.append(item)

    release_attachments = [Attachment.from_json(a) for a in normalized_attachments]

    force_reclearing_flag = os.getenv(
        "FORCE_RECLEARING_FLAG", default=DEFAULT_FORCE_RECLEARING_FLAG
    )
    if force_reclearing_flag not in release.data.get("additionalData", {}).keys():
        # Verify if a clearing report already exists
        if list(
            filter(
                lambda x: (
                    x.attachmentType == "CLEARING_REPORT"
                    or x.attachmentType == "COMPONENT_LICENSE_INFO_XML"
                ),
                release_attachments,
            )
        ):
            release.workflow_summary.upload_status = UploadStatus.CLEARED
            return None
    return release_attachments


def skip_not_oss_component(release_info: Release):
    release_info.skip_upload = True
    if not release_info.workflow_summary.upload_status == UploadStatus.SW360_ERROR:
        release_info.workflow_summary.upload_status = UploadStatus.NOT_OSS
        logger.warning(
            f"Skip {release_info.name} for {release_info.componentType} component"
        )
    else:
        logger.error(
            f"Skip {release_info.name} because component is not accessible in SW360"
        )


def skip_already_scanned_component(release_info: Release):
    release_info.skip_upload = True
    release_info.workflow_summary.upload_status = UploadStatus.ALREADY_SCANNED
    logger.warning(
        f"Skip {release_info.name} for {release_info.clearingState} component"
    )


def wait_for_completion_expected_agents(
    foss: Fossology, upload: Upload, mandatory_agents: list[str], timeout: int = 300
) -> bool:
    """Check if all mandatory agents have completed their jobs on an upload.

    Args:
        foss: Fossology instance
        upload: Upload object to check
        mandatory_agents: List of agent names that must complete
        timeout: Maximum time to wait in seconds

    Returns:
        True if all agents completed, False if timeout reached
    """

    @retry(
        retry=retry_if_result(lambda result: not result),
        stop=stop_after_delay(timeout),
        wait=wait_fixed(10),
    )
    def check_agents_completion() -> bool:
        try:
            jobs = foss.jobs_history(upload=upload)
        except Exception as e:
            logger.warning(
                f"Error while checking agents for {upload.uploadname}, will retry: {e}"
            )
            return False
        all_agents_completed = True

        for job in jobs:
            for agent in job.jobQueue:
                if agent.jobQueueType in mandatory_agents and agent.isInProgress:
                    logger.debug(
                        f"Agent {agent.jobQueueType} is still running for upload {upload.uploadname}, waiting for completion"
                    )
                    all_agents_completed = False
                    break
            if not all_agents_completed:
                break

        return all_agents_completed

    try:
        return check_agents_completion()
    except RetryError:
        logger.warning(
            f"Timeout reached while waiting for agents to complete for upload {upload.uploadname}"
        )
        return False


def agents_started_or_completed(
    foss: Fossology, upload: Upload, mandatory_agents: list[str]
) -> bool:
    jobs = foss.jobs_history(upload=upload)
    started_or_completed_agents = set()
    for job in jobs:
        for agent in job.jobQueue:
            if agent.status in ["Completed", "Queued", "Started"]:
                started_or_completed_agents.add(agent.jobQueueType)
    if not started_or_completed_agents.issuperset(set(mandatory_agents)):
        return False
    return True


def get_upload_release_id(upload: Upload):
    return upload.description.split(",")[0]


def get_clearing_complexity(num: int) -> str:
    try:
        num = int(num)
    except ValueError:
        return "Invalid number"

    if num <= 100:
        complexity = ClearingComplexity.VERY_SMALL
    elif num <= 1000:
        complexity = ClearingComplexity.SMALL
    elif num <= 5000:
        complexity = ClearingComplexity.MEDIUM
    elif num <= 10000:
        complexity = ClearingComplexity.LARGE
    else:
        complexity = ClearingComplexity.VERY_LARGE
    return complexity.name


def estimate_clearing_effort(total_files_to_be_cleared: int) -> float:
    complexity = get_clearing_complexity(total_files_to_be_cleared)
    return EffortEstimation[complexity].value
