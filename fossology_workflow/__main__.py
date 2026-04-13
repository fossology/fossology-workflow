# Copyright (c) Siemens 2020
# SPDX-License-Identifier: MIT

import logging
import os
import sys
from datetime import datetime

import click
import coloredlogs

from fossology_workflow import settings
from fossology_workflow.clearing import Clearing

today = datetime.now().strftime("%Y-%m-%d_%H:%M")
separator = "==================================================================================="

logger = logging.getLogger("fossology_workflow.main")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(name)s: %(message)s",
    filename=f"automated-workflow-{today}.log",
    filemode="w+",
)
formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s: %(message)s")
coloredlogs.install(
    level="DEBUG",
    fmt="%(asctime)s | %(levelname)s | %(name)s: %(message)s",
    isatty=False,
)

# Limit loglevel for all other loggers
logging.getLogger("urllib3").setLevel(logging.CRITICAL)
logging.getLogger("chardet").setLevel(logging.CRITICAL)
logging.getLogger("fossology.folders").setLevel(logging.ERROR)
logging.getLogger("fossology.uploads").setLevel(logging.ERROR)
logging.getLogger("fossology.jobs").setLevel(logging.ERROR)


def do_clearing(config: settings.Config, clearing: Clearing):
    # Get all sources attachments and upload status
    # Upload source attachments to Fossology if config allows it
    logger.info(separator)
    logger.info(
        f"Downloading sources from project {clearing.project.name} on {clearing.sw360.url}"
    )
    clearing.upload_sources()

    # Upload reports to SW360
    if config.REPORTS_TO_SW360:
        existing_uploads = list(
            filter(lambda x: x.fossology_upload, clearing.project.linked_releases)
        )
        logger.info(separator)
        logger.info(
            f"Uploading reports for the {len(existing_uploads)} uploads of this release "
            f"from {clearing.foss.host} back to {clearing.sw360.url}"
        )
        clearing.upload_reports()

    clearing.workflow_summary()
    clearing.workflow_metrics()
    clearing.log_summary()


@click.group()
def cli():
    """A simple CLI for the clearing automation."""
    pass


@click.command()
def request_clearing():
    """
    Request a clearing for a given project and release.

    \b
    Make sure one of SW360_PROJECT or SW360_CR is set in the environment:
    - SW360_PROJECT: The SW360 project id
    - SW360_CR: The SW360 clearing request id
    """
    config = settings.Config()
    config.SW360_PROJECT = os.getenv("SW360_PROJECT", None)
    config.SW360_CR = os.getenv("SW360_CR", None)
    if not (config.SW360_PROJECT or config.SW360_CR):
        sys.exit("One of SW360_PROJECT or SW360_CR is missing from the environment")
    clearing = Clearing(config)
    clearing.get_sw360_project()
    do_clearing(config, clearing)


@click.command()
def create_initial_reports():
    """
    \b
    Create initial reports for the latest releases uploaded to SW360.
    """
    config = settings.Config()
    clearing = Clearing(config)
    clearing.get_last_releases()
    do_clearing(config, clearing)


cli.add_command(request_clearing)
cli.add_command(create_initial_reports)

if __name__ == "__main__":
    cli()
