# Copyright (c) Siemens 2020
# SPDX-License-Identifier: MIT

import os
import sys

from fossology_workflow.helpers import strtobool


class Config:
    def __init__(self) -> None:
        self.SW360_URL = os.getenv("SW360_URL") or sys.exit(
            "SW360_URL is missing from the environment"
        )
        self.SW360_TOKEN = os.getenv("SW360_TOKEN") or sys.exit(
            "SW360_TOKEN is missing from the environment"
        )
        self.SW360_PROJECT = os.getenv("SW360_PROJECT") or None
        self.SW360_CR = os.getenv("SW360_CR") or None
        self.FOSSOLOGY_URL = os.getenv("FOSSOLOGY_URL") or sys.exit(
            "FOSSOLOGY_URL is missing from the environment"
        )
        self.FOSSOLOGY_TOKEN = os.getenv("FOSSOLOGY_TOKEN") or sys.exit(
            "FOSSOLOGY_TOKEN is missing from the environment"
        )
        self.FOSSOLOGY_FOLDER = os.getenv("FOSSOLOGY_FOLDER") or sys.exit(
            "FOSSOLOGY_FOLDER is missing from the environment"
        )
        self.FOSSOLOGY_GROUP = os.getenv("FOSSOLOGY_GROUP") or sys.exit(
            "FOSSOLOGY_GROUP is missing from the environment"
        )
        self.REPORTS_TO_SW360 = strtobool(
            os.getenv("REPORTS_TO_SW360", default="false")
        )
        self.UPLOADS_TO_FOSSOLOGY = strtobool(
            os.getenv("UPLOADS_TO_FOSSOLOGY", default="false")
        )
        self.BATCH_SIZE = os.getenv("BATCH_SIZE", default=20)
        self.REUSE = strtobool(os.getenv("REUSE", default="false"))
        self.UPLOAD_INITIAL_SCAN_REPORT = strtobool(
            os.getenv("UPLOAD_INITIAL_SCAN_REPORT", default="false")
        )
        self.FOSS_REPORT_WAITING_TIME = os.getenv(
            "FOSS_REPORT_WAITING_TIME", default=10
        )
        self.DEFAULT_JOB_SPEC = {
            "analysis": {
                "bucket": False,
                "copyright_email_author": True,
                "ecc": True,
                "ipra": True,
                "keyword": True,
                "monk": True,
                "mime": True,
                "nomos": True,
                "ojo": True,
                "package": True,
                "patent": True,
            },
            "decider": {
                "nomos_monk": False,
                "bulk_reused": False,
                "new_scanner": False,
                "ojo_decider": False,
            },
            "reuse": {
                "reuse_upload": 0,
                "reuse_group": self.FOSSOLOGY_GROUP,
                "reuse_main": True,
                "reuse_enhanced": False,
                "reuse_report": False,
                "reuse_copyright": True,
            },
        }
        self.MANDATORY_AGENTS_ISR = [
            "ununpack",
            "adj2nest",
            "copyright",
            "ecc",
            "keyword",
            "monk",
            "mimetype",
            "nomos",
            "ojo",
        ]
