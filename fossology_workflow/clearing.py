# Copyright (c) Siemens 2020
# SPDX-License-Identifier: MIT

import csv
import logging
import os
import sys
from datetime import date, datetime, timedelta
from http.client import RemoteDisconnected
from pathlib import Path
from typing import Optional, Tuple

import sw360
from fossology import Fossology
from fossology.enums import AccessLevel, ReportFormat
from fossology.exceptions import FossologyApiError
from fossology.obj import Folder, Upload
from requests.exceptions import ConnectionError
from tenacity import RetryError
from urllib3.exceptions import ProtocolError

from fossology_workflow.helpers import (
    agents_started_or_completed,
    estimate_clearing_effort,
    extract_resource_id,
    get_clearing_complexity,
    get_filesha1,
    get_release_attachments,
    get_source_attachment,
    get_upload_release_id,
    initial_scan_available,
    normalize_release_name,
    normalize_report_name,
    skip_already_scanned_component,
    skip_not_oss_component,
    wait_for_completion_expected_agents,
)
from fossology_workflow.models import (
    Attachment,
    Project,
    Release,
    ReleasesProject,
    ReportMetric,
    ReportStatus,
    UploadMetric,
    UploadStatus,
    WorkflowSummary,
)
from fossology_workflow.settings import Config

logger = logging.getLogger(__name__)

DEFAULT_IGNORE_FLAG = "WF:ignore"


class Clearing:
    def __init__(self, config: Config):
        try:
            self.sw360 = sw360.SW360(config.SW360_URL, config.SW360_TOKEN, oauth2=True)
            self.sw360.login_api(config.SW360_TOKEN)
            logger.info(f"Connected with SW360 server {self.sw360.url}")
        except sw360.SW360Error as exception:
            logger.error(
                f"Unable to login on {config.SW360_URL}, maybe your token expired."
            )
            sys.exit(exception.message)

        try:
            self.foss = Fossology(
                config.FOSSOLOGY_URL, config.FOSSOLOGY_TOKEN, version="v1"
            )
            logger.info(
                f"Connected as {self.foss.user.name} with Fossology server {self.foss.host}"
                f" using API version {self.foss.info.version}"
            )
        except FossologyApiError as exception:
            logger.error(
                f"Unable to login on {config.FOSSOLOGY_URL}, maybe your token expired."
            )
            sys.exit(exception.message)

        self.group = config.FOSSOLOGY_GROUP
        self.clearing_folder = self.foss.detail_folder(int(config.FOSSOLOGY_FOLDER))
        try:
            self.folders = self.foss.list_folders()
        except FossologyApiError as ex:
            sys.exit(
                f"Error while retrieving list of folders or uploads from {self.foss.host}: {ex.message}"
            )

        # Get config options
        self.sw360_cr = config.SW360_CR
        self.sw360_project = config.SW360_PROJECT
        self.batch_size = config.BATCH_SIZE
        self.reuse = config.REUSE
        self.upload_initial_scan_report = config.UPLOAD_INITIAL_SCAN_REPORT
        self.uploads_to_fossology = config.UPLOADS_TO_FOSSOLOGY
        self.reports_to_sw360 = config.REPORTS_TO_SW360
        self.foss_report_waiting_time = config.FOSS_REPORT_WAITING_TIME
        self.mandatory_agents = config.MANDATORY_AGENTS_ISR

        # Collect list of relevant uploads for this particular project
        self.project = Project()
        self.workflow_summary_filename = ""
        self.upload_metric = UploadMetric()
        self.report_metric = ReportMetric()
        logger.info(
            "==================================================================================="
        )
        logger.info("Config:")
        logger.info(f"  - fossology upload folder: {self.clearing_folder}")
        logger.info(f"  - REUSE: {self.reuse}")
        logger.info(
            f"  - UPLOAD_INITIAL_SCAN_REPORT: {self.upload_initial_scan_report}"
        )
        logger.info(f"  - UPLOADS_TO_FOSSOLOGY: {self.uploads_to_fossology}")
        logger.info(f"  - REPORTS_TO_SW360: {self.reports_to_sw360}")
        logger.info(
            "==================================================================================="
        )

    def is_oss_component(self, release: Release) -> bool:
        component_url = ""
        if links := release.data.get("_links"):
            if component := links.get("sw360:component"):
                component_url = component.get("href")
        try:
            component = self.sw360.get_component_by_url(component_url)
        except sw360.SW360Error as exc:
            release.workflow_summary.upload_status = UploadStatus.SW360_ERROR
            logger.error(
                f"Error while accessing component {release.id}: {exc.response}"
            )
            return False
        release.componentType = component.get("componentType")
        return release.componentType in ("OSS", "CODE_SNIPPET")

    def get_release_data(self, release_id: str) -> Optional[dict]:
        try:
            release_data = self.sw360.get_release(release_id)
        except Exception:
            logger.error(
                f"Error while getting release data for the following release: {release_id}"
            )
            return None
        return release_data

    def get_releases(self, recent_releases: list = []) -> None:
        logger.info(
            f"Gathering releases for project {self.project.name} "
            f"({self.project.id} - clearingRequestId {self.project.clearingRequestId})"
        )
        skipped_already_cleared_releases: int = 0
        if recent_releases:
            list_of_releases = recent_releases
        else:
            list_of_releases = self.project.data["linkedReleases"]
        for release in list_of_releases:
            if recent_releases:
                release_id = release["id"]
                release_data = release
            else:
                release_id = extract_resource_id(release.get("release"))
                if [
                    release
                    for release in self.project.linked_releases
                    if release.id == release_id
                ]:
                    logger.info(
                        f"Release {release_id} already exists in project {self.project.id}."
                    )
                    continue

                # Fetch full release data only when needed
                release_data = self.get_release_data(release_id)
                if release_data is None:
                    continue

            if recent_releases:
                three_months_ago = datetime.now() - timedelta(days=90)
                created_on = datetime.strptime(
                    release_data.get("createdOn"), "%Y-%m-%d"
                )
                if created_on < three_months_ago:
                    logger.info(
                        f"Skipping release {release_id}: older than three months"
                    )
                    continue

            workflow_summary = WorkflowSummary(
                upload_status=UploadStatus.UNKNOWN,
                report_status=ReportStatus.UNKNOWN,
                reuse_info="",
                url="",
            )
            release_info = Release(
                id=release_id,
                name=release_data.get("name"),
                version=release_data.get("version"),
                clearingState=release_data.get("clearingState"),
                componentType="",
                data=release_data,
                skip_upload=False,
                workflow_summary=workflow_summary,
                fossology_upload=None,
                fossology_upload_summary=None,
            )
            if not self.is_oss_component(release_info):
                skip_not_oss_component(release_info)
            if release_info.clearingState in (
                "REPORT_AVAILABLE",
                "APPROVED",
            ):
                skip_already_scanned_component(release_info)
                skipped_already_cleared_releases += 1
            self.project.linked_releases.append(release_info)
        logger.info(
            f"Project {self.project.name} has {len(self.project.linked_releases)} linked releases "
            f"({skipped_already_cleared_releases} are already cleared)"
        )

    def get_last_releases(self):
        recent_releases = self.sw360.get_all_releases(
            isNewClearingWithSourceAvailable=True, all_details=True
        )
        self.project = ReleasesProject()
        self.get_releases(recent_releases)

    def get_sw360_project(self):
        if self.sw360_cr:
            sw360_cr = self.sw360.get_clearing_request(self.sw360_cr)
            sw360_project_id = sw360_cr.get("projectId")
        else:
            sw360_project_id = self.sw360_project
        self.project.id = sw360_project_id
        # TODO check whether filtering is possible at project level
        self.project.data = self.sw360.get_project(sw360_project_id)
        self.project.name = self.project.data["name"]
        self.project.clearingRequestId = self.project.data.get(
            "clearingRequestId", None
        )
        self.project.linked_releases = []
        self.get_releases()

    def upload_sources(self):
        # Iterate through all linked releases
        uploads = pending = 0
        for release in self.project.linked_releases:
            if release.skip_upload:
                continue
            if uploads < int(self.batch_size):
                if self.get_release_source(release):
                    uploads += 1
                    logger.info(
                        f"{release.name} ({release.version}) UPLOADED ({uploads})"
                    )
                else:
                    status = release.workflow_summary.upload_status
                    if status in (
                        UploadStatus.EXISTS,
                        UploadStatus.CLEARED,
                        UploadStatus.DO_NOT_UPLOAD,
                    ):
                        logger.debug(
                            f"{release.name} ({release.version}) {status.value}"
                        )
                    else:
                        logger.error(
                            f"{release.name} ({release.version}) {status.value}"
                        )
            else:
                pending += 1
                release.workflow_summary.upload_status = UploadStatus.PENDING
        logger.info(
            f"A total of {uploads} files have been uploaded for this project ({pending} still pending)"
        )

    def source_already_exists(
        self, subfolder: Folder, source: str, release_id: str
    ) -> tuple[Optional[Upload], bool]:
        """
        Verify if source file has already been uploaded
        And all expected job where performed
        """
        for upload in self.foss.list_uploads(
            folder=subfolder, group=self.group, all_pages=True
        )[0]:
            upload_release_id = get_upload_release_id(upload)
            if upload.uploadname == source and upload_release_id == release_id:
                # Verify if jobs are completed
                return (
                    upload,
                    agents_started_or_completed(
                        self.foss, upload, self.mandatory_agents
                    ),
                )
        return (None, False)

    def get_reuse_upload(self, folder: Folder, upload: Upload) -> Upload:
        last_upload_date = None
        last_cleared_upload = None
        uploads, _ = self.foss.list_uploads(
            folder=folder, all_pages=True, group=self.group
        )
        for upload in uploads:
            try:
                summary = self.foss.upload_summary(upload, self.group)
                if summary.clearingStatus != "Closed":
                    continue
                upload_date = upload.uploaddate.split(" ")[0]
                if not last_upload_date or date.fromisoformat(
                    upload_date
                ) > date.fromisoformat(last_upload_date):
                    last_upload_date = upload_date
                    last_cleared_upload = upload
            except FossologyApiError as exc:
                logger.error(
                    f"Error while getting summary for reusable upload {upload.uploadname}: {exc.message}"
                )
                continue
        return last_cleared_upload

    def get_release_source(self, release: Release) -> bool:
        ignore_flag = os.getenv("IGNORE_FLAG", default=DEFAULT_IGNORE_FLAG)
        if ignore_flag in release.data.get("additionalData", {}).keys():
            release.workflow_summary.upload_status = UploadStatus.IGNORED
            return False

        if attachments := get_release_attachments(release):
            if source := get_source_attachment(attachments, release):
                return self.upload_source(source, release)
        return False

    def upload_source_to_fossology(
        self, subfolder: Folder, filename: str, description: str, release: Release
    ) -> Optional[Upload]:
        try:
            upload = self.foss.upload_file(
                subfolder,
                filename,
                description=description,
                access_level=AccessLevel.PUBLIC,
                group=self.group,
            )
        except FossologyApiError as exc:
            logger.error(
                f"File {filename} ({description}) could not be uploaded to Fossology: {exc.message}"
            )
            release.workflow_summary.upload_status = UploadStatus.EMPTY
            return None
        except RetryError:
            logger.error(
                f"File {filename} ({description}) takes too long to upload, try manually"
            )
            release.workflow_summary.upload_status = UploadStatus.EMPTY
            return None
        if upload.hash.sha1 != get_filesha1(filename):
            logger.error(
                f"File {filename} uploaded into Fossology has the wrong SHA1 value: "
                f"upload sha1 = {upload.hash.sha1}, local file sha1 = {get_filesha1(filename)}"
            )
            release.workflow_summary.upload_status = UploadStatus.CORRUPT
            return None
        return upload

    def create_subfolder(self, release_name: str) -> Folder | None:
        subfolder: Folder = None
        for folder in self.folders:
            if folder.name == release_name and folder.parent == self.clearing_folder.id:
                return folder
        if not subfolder:
            subfolder = self.foss.create_folder(
                self.clearing_folder, release_name, group=self.group
            )
            self.folders.append(subfolder)
            return subfolder

    def upload_source(self, attachment: Attachment, release: Release) -> bool:
        # Verify if a source file with the same name
        # already exists in the same subfolder on fossology
        release_name = normalize_release_name(release.name)
        subfolder = self.create_subfolder(release_name)
        logger.info(f"Using subfolder {subfolder} ({subfolder.id})")
        filename = attachment.filename
        upload, expected_jobs = self.source_already_exists(
            subfolder, filename, release.id
        )
        if upload:
            logger.info(f"Upload {upload.uploadname} ({upload.id}) already exists")
            release.fossology_upload = upload
            release.workflow_summary.upload_status = UploadStatus.EXISTS
            release.workflow_summary.url = (
                f"{self.foss.host}/?mod=browse&folder={upload.folderid}"
            )
            if not self.reuse and expected_jobs:
                return False

        if not self.uploads_to_fossology:
            # Do not upload new files to Fossology due to config
            release.workflow_summary.upload_status = UploadStatus.DO_NOT_UPLOAD
            return False

        if upload and not expected_jobs:
            release.workflow_summary.upload_status = UploadStatus.JOBS_SCHEDULED
            logger.debug(f"Reschedule jobs for {upload.uploadname}")

        if not upload:
            # Download attachment source
            attachment_id = (
                extract_resource_id(attachment._links["self"]["href"])
                if attachment._links.get("self")
                else attachment.attachmentContentId
            )
            try:
                self.sw360.download_release_attachment(
                    filename, release.id, attachment_id
                )
            except sw360.SW360Error as exc:
                logger.error(
                    f"Failed to download attachment {filename} for release {release.name} ({release.version}): {exc.response}"
                )
                release.workflow_summary.upload_status = UploadStatus.NO_SOURCE_SPEC
                return False

            # Upload file and verify the SHA1
            logger.info(f"Uploading {filename} to folder {release_name} ({release.id})")
            description = f"{release.id}, {release_name}, {release.version}"
            if self.project.clearingRequestId:
                description += f", clearingRequestId {self.project.clearingRequestId}"
            if upload := self.upload_source_to_fossology(
                subfolder, filename, description, release
            ):
                # Add upload to list of uploads for this particular component
                # And link upload object to release
                # Remove file from local filesystem
                Path(filename).unlink()
                release.workflow_summary.upload_status = UploadStatus.UPLOADED
                release.fossology_upload = upload
                release.workflow_summary.url = (
                    f"{self.foss.host}/?mod=browse&folder={subfolder.id}"
                )
            else:
                # Upload failed
                # Remove file from local filesystem
                Path(filename).unlink()
                return False

        # Get existing clearing results
        job_spec, last_upload = self.get_job_spec_with_reuse(subfolder, upload, release)

        # Start configured jobs
        if not self.reuse or (self.reuse and last_upload):
            if not self.schedule_jobs(
                upload, subfolder, release, release_name, job_spec
            ):
                return False
        return True

    def get_job_spec_with_reuse(
        self, subfolder: Folder, upload: Upload, release: Release
    ) -> Tuple[dict, Upload]:
        job_spec = Config().DEFAULT_JOB_SPEC
        if last_upload := self.get_reuse_upload(subfolder, upload):
            if self.reuse:
                logger.info(
                    f"New upload {upload.uploadname} will reuse clearing data "
                    f"from upload {last_upload.uploadname}"
                )
                job_spec["reuse"]["reuse_upload"] = last_upload.id
            else:
                logger.info(
                    f"New upload {upload.uploadname} would reuse clearing data "
                    f"from upload {last_upload.uploadname} if environment variable REUSE would be set to 'true'"
                )
            release.workflow_summary.reuse_info = (
                f"{last_upload.uploadname} (from {last_upload.uploaddate})"
            )
        return job_spec, last_upload

    def schedule_jobs(
        self,
        upload: Upload,
        subfolder: Folder,
        release: Release,
        release_name: str,
        job_spec: dict,
    ) -> bool:
        try:
            self.foss.schedule_jobs(subfolder, upload, job_spec, group=self.group)
            logger.info(f"Jobs have been started for {release_name}")
        except FossologyApiError as exc:
            logger.error(
                f"Error while scheduling jobs for {upload.uploadname} ({upload.id}): {exc.message}"
            )
            release.workflow_summary.upload_status = UploadStatus.UNSCHEDULED
            return False
        return True

    def upload_sw360_reports(self, release: Release):
        if release.fossology_upload_summary.clearingStatus == "Closed":
            uploaded_reports = 0
            for report_format in (ReportFormat.UNIFIEDREPORT, ReportFormat.CLIXML):
                report, report_name = self.generate_and_download_report(
                    release, report_format
                )
                if report:
                    upload_type = (
                        "COMPONENT_LICENSE_INFO_XML"
                        if report_format == ReportFormat.CLIXML
                        else "CLEARING_REPORT"
                    )
                    report_name = normalize_report_name(report_name)
                    if self.upload_attachment(
                        report, report_name, upload_type, release
                    ):
                        uploaded_reports += 1
                        logger.info(
                            f"{report_name} has been uploaded as {upload_type} "
                            f"to release {release.name} ({release.version})"
                        )
            if uploaded_reports == 2:
                release.workflow_summary.report_status = ReportStatus.UPLOADED
        else:
            report, report_name = self.generate_and_download_report(
                release, ReportFormat.SPDX2
            )
            if report:
                upload_type = "INITIAL_SCAN_REPORT"
                if self.upload_attachment(report, report_name, upload_type, release):
                    release.workflow_summary.report_status = ReportStatus.UPLOADED
                    logger.info(
                        f"{report_name} has been uploaded as {upload_type} "
                        f"to release {release.name} ({release.version})"
                    )

    def generate_and_download_report(
        self, release: Release, format: str
    ) -> Tuple[str, str]:
        try:
            report_id = self.foss.generate_report(
                release.fossology_upload, report_format=format, group=self.group
            )
            return self.foss.download_report(
                report_id, group=self.group, wait_time=self.foss_report_waiting_time
            )
        except FossologyApiError as ex:
            logger.error(
                f"Error while generating or downloaded report for {release.fossology_upload.id}: {ex}"
            )
        except RetryError:
            logger.error(
                f"Report for {release.fossology_upload.id} takes too long to generate, try manually"
            )
        release.workflow_summary.report_status = ReportStatus.FOSSOLOGY_ERROR
        return ("", "")

    def upload_attachment(
        self,
        report: str,
        report_name: str,
        upload_type: str,
        release: Release,
    ) -> bool:
        try:
            with open(report_name, "wb") as report_file:
                report_file.write(report)
            self.sw360.upload_release_attachment(
                release.id, report_name, upload_type=upload_type
            )
            Path(report_name).unlink()
        except Exception as ex:
            logger.error(f"Error while uploading report for release {release.id}: {ex}")
            Path(report_name).unlink()
            release.workflow_summary.report_status = ReportStatus.SW360_ERROR
            return False
        return True

    def get_summary_and_upload_report(self, release: Release):
        if not wait_for_completion_expected_agents(
            self.foss, release.fossology_upload, self.mandatory_agents
        ):
            logger.error(
                f"Timeout: mandatory agents didn't complete in time for {release.fossology_upload.uploadname}"
            )
            release.workflow_summary.report_status = ReportStatus.FOSSOLOGY_ERROR
            return
        # Collect clearing status from Fossology upload
        try:
            release.fossology_upload_summary = self.foss.upload_summary(
                release.fossology_upload, group=self.group
            )
        except FossologyApiError as exc:
            logger.error(
                f"Error while getting summary for upload {release.fossology_upload.uploadname} "
                f"({release.fossology_upload.id}): {exc.message}"
            )
            release.workflow_summary.report_status = ReportStatus.FOSSOLOGY_ERROR
            return

        logger.info(
            f"{release.fossology_upload.uploadname} ({release.fossology_upload.id}) clearing status: "
            f"{release.fossology_upload_summary.clearingStatus}, "
            f"{release.fossology_upload_summary.filesToBeCleared} files to be cleared"
        )

        # Upload report back to SW360 if conditions are met
        if (
            release.fossology_upload_summary.clearingStatus != "Closed"
            and self.upload_initial_scan_report
            and not initial_scan_available(get_release_attachments(release))
        ) or release.fossology_upload_summary.clearingStatus == "Closed":
            self.upload_sw360_reports(release)

    def upload_reports(self):
        # Get available uploads and clearing summary
        for release in self.project.linked_releases:
            if release.fossology_upload:
                try:
                    self.get_summary_and_upload_report(release)
                except (RemoteDisconnected, ProtocolError, ConnectionError) as e:
                    logger.error(
                        f"Network error processing release {release.fossology_upload.uploadname}: {e}"
                    )
                    continue

    def workflow_summary(self):  # noqa: C901
        self.workflow_summary_filename = (
            f"workflow-summary-{self.project.name.replace('/', '')}.csv"
        )
        with open(self.workflow_summary_filename, "w") as wm:
            csv_writer = csv.writer(wm, delimiter=",")
            header = [
                "Project",
                "Subject",
                "Clearing Status",
                "Fossology Status",
                "Upload status",
                "Report status (or number of remaining files to be cleared)",
                "Complexity",
                "Fossology Url",
                "Reuse Info",
            ]
            csv_writer.writerow(header)
            estimated_effort = 0
            for release in self.project.linked_releases:
                reuse_info = ""
                if self.reuse:
                    reuse_info = release.workflow_summary.reuse_info
                elif release.workflow_summary.reuse_info and not self.reuse:
                    reuse_info = f"{release.workflow_summary.reuse_info} => set REUSE=true to effectively use it"

                report_status = ""
                complexity = ""
                if release.workflow_summary.report_status == ReportStatus.UNKNOWN:
                    if (
                        release.fossology_upload_summary
                        and release.fossology_upload_summary.filesToBeCleared
                    ):
                        num = release.fossology_upload_summary.filesToBeCleared
                        estimated_effort += estimate_clearing_effort(int(num))
                        report_status = f"{num}"
                        complexity = get_clearing_complexity(num)
                else:
                    report_status = release.workflow_summary.report_status.name

                fossology_status = ""
                if (
                    release.fossology_upload_summary
                    and release.fossology_upload_summary.clearingStatus
                ):
                    fossology_status = release.fossology_upload_summary.clearingStatus

                row = [
                    self.project.name,
                    f"{release.name} {release.version}",
                    release.clearingState,
                    fossology_status,
                    release.workflow_summary.upload_status.name,
                    report_status,
                    complexity,
                    release.workflow_summary.url,
                    reuse_info,
                ]
                csv_writer.writerow(row)

            if estimated_effort:
                csv_writer.writerow([])
                summary_text = (
                    f"Estimated time required for clearing: {estimated_effort} hours"
                )
                summary_row = [summary_text] + [""] * (len(header) - 1)
                csv_writer.writerow(summary_row)

    def workflow_metrics(self):
        for release in self.project.linked_releases:
            self.upload_metric.total += 1
            if release.workflow_summary.upload_status in (
                UploadStatus.EXISTS,
                UploadStatus.JOBS_SCHEDULED,
                UploadStatus.ALREADY_SCANNED,
            ):
                self.upload_metric.exists += 1
            elif release.workflow_summary.upload_status == UploadStatus.UPLOADED:
                self.upload_metric.uploaded += 1
            elif release.workflow_summary.upload_status in (
                UploadStatus.PENDING,
                UploadStatus.UNSCHEDULED,
            ):
                self.upload_metric.pending += 1
            elif release.workflow_summary.upload_status == UploadStatus.CLEARED:
                self.upload_metric.cleared += 1
            elif release.workflow_summary.upload_status == UploadStatus.NOT_OSS:
                self.upload_metric.not_oss += 1
            elif release.workflow_summary.upload_status in (
                UploadStatus.IGNORED,
                UploadStatus.DO_NOT_UPLOAD,
            ):
                self.upload_metric.ignored += 1
            else:
                self.upload_metric.error += 1

            self.report_metric.total += 1
            if release.workflow_summary.report_status == ReportStatus.UPLOADED:
                self.report_metric.uploaded += 1
            elif release.workflow_summary.report_status in (
                ReportStatus.FOSSOLOGY_ERROR,
                ReportStatus.SW360_ERROR,
            ):
                self.report_metric.error += 1

    def log_summary(self):
        logger.info(
            "==================================================================================="
        )
        logger.info(
            f"Upload summary for project {self.project.name} with {self.upload_metric.total} releases"
        )
        logger.info(f"Uploaded files: {self.upload_metric.uploaded}")
        logger.info(f"Existing files: {self.upload_metric.exists}")
        logger.info(f"Already cleared: {self.upload_metric.cleared}")
        logger.info(
            f"Pending releases: {self.upload_metric.pending} (due to batch upload)"
        )
        logger.info(f"Not an OSS component: {self.upload_metric.not_oss}")
        logger.info(f"Ignored releases: {self.upload_metric.ignored}")
        logger.info(f"Errors: {self.upload_metric.error}")
        logger.info(
            "==================================================================================="
        )
        logger.info(
            f"Report summary for project {self.project.name} with {self.report_metric.total} reports"
        )
        logger.info(f"Uploaded: {self.report_metric.uploaded}")
        logger.info(f"Errors: {self.report_metric.error}")
        logger.info(
            "==================================================================================="
        )
        logger.info(
            f"Full report about upload status available as '{self.workflow_summary_filename}'"
        )
