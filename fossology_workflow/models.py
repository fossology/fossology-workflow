# Copyright (c) Siemens 2020
# SPDX-License-Identifier: MIT

from dataclasses import dataclass, field, fields
from datetime import datetime
from enum import Enum
from typing import List

from fossology.obj import Summary, Upload


class UploadStatus(Enum):
    UPLOADED = "uploaded to fossology"
    NOT_OSS = "component type is neither OSS nor CODE_SNIPPET"
    ALREADY_SCANNED = "component has already been scanned, reported or cleared"
    NO_SOURCE = "no source attachment available"
    MULTIPLE_SOURCE = "multiple source attachments found"
    NO_SOURCE_SPEC = "specified source not found"
    MULTIPLE_SOURCE_SPEC = "multiple specified source attachments"
    CLEARED = "clearing report already available"
    IGNORED = "release ignored by flag"
    EXISTS = "release source already exists in fossology"
    EMPTY = "upload returned by fossology is empty"
    CORRUPT = "wrong file sha1 on fossology"
    PENDING = "not analyzed yet"
    DO_NOT_UPLOAD = "source file not uploaded"
    UNKNOWN = "has not been set"
    SW360_ERROR = "error while getting data from SW360"
    UNSCHEDULED = "error while scheduling jobs"
    JOBS_SCHEDULED = "upload already exist but jobs where missing"


class ClearingComplexity(Enum):
    VERY_SMALL = "0-100 files needs to be cleared"
    SMALL = "101-1000 files needs to be cleared"
    MEDIUM = "1001-5000 files needs to be cleared"
    LARGE = "5001-10000 files needs to be cleared"
    VERY_LARGE = "More than 10000 files needs to be cleared"


class EffortEstimation(Enum):
    VERY_SMALL = 0.5
    SMALL = 2
    MEDIUM = 5
    LARGE = 12
    VERY_LARGE = 20


class ReportStatus(Enum):
    SW360_ERROR = "error while uploading report to SW360"
    FOSSOLOGY_ERROR = "error while generating or download report from Fossology"
    UPLOADED = "report has been uploaded"
    UNKNOWN = "has not been set"


@dataclass
class WorkflowSummary:
    upload_status: UploadStatus = UploadStatus.UNKNOWN
    report_status: ReportStatus = ReportStatus.UNKNOWN
    url: str = ""
    reuse_info: str = ""


@dataclass
class Release:
    id: str
    name: str
    version: str
    clearingState: str
    componentType: str
    data: dict
    skip_upload: bool
    fossology_upload: Upload
    fossology_upload_summary: Summary
    workflow_summary: WorkflowSummary


@dataclass
class UploadMetric:
    total: int = 0
    uploaded: int = 0
    exists: int = 0
    cleared: int = 0
    error: int = 0
    pending: int = 0
    not_oss: int = 0
    ignored: int = 0


@dataclass
class ReportMetric:
    total: int = 0
    uploaded: int = 0
    error: int = 0


@dataclass
class Attachment:
    filename: str = ""
    sha1: str = ""
    attachmentType: str = ""
    attachmentContentId: str = ""
    _links: dict = field(default_factory=dict)

    @classmethod
    def from_json(cls, json_dict: dict) -> "Attachment":
        allowed_keys = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in json_dict.items() if k in allowed_keys}
        return cls(**filtered)


class Project:
    id: str
    name: str
    clearingRequestId: str
    data: dict
    linked_releases: List[Release]


class ReleasesProject:
    def __init__(self):
        self.id = "0"
        self.name = f"Last releases {datetime.now().strftime('%Y-%m-%d_%H:%M')}"
        self.clearingRequestId = "0"
        self.data = {}
        self.linked_releases = []
