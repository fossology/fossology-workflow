# Copyright (c) Siemens 2020
# SPDX-License-Identifier: MIT

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from fossology_workflow.clearing import Clearing
from fossology_workflow.models import ReleasesProject


def test_get_release_data(ClearingObj: Clearing):
    release_id = "1234567890"

    ClearingObj.sw360.get_release = MagicMock(
        return_value={"id": release_id, "name": "Test Release"}
    )
    release_data = ClearingObj.get_release_data(release_id)

    assert release_data is not None
    assert release_data["id"] == release_id
    ClearingObj.sw360.get_release.assert_called_once_with(release_id)

    ClearingObj.sw360.get_release = MagicMock(side_effect=Exception("API failure"))
    with patch("fossology_workflow.clearing.logger.error") as mock_logger:
        release_data = ClearingObj.get_release_data(release_id)
        assert release_data is None
        mock_logger.assert_called_once_with(
            f"Error while getting release data for the following release: {release_id}"
        )


def test_last_releases_within_three_months(
    ClearingObj: Clearing, LastReleases: list, ReleaseData: dict
):
    ClearingObj.project = None

    ClearingObj.sw360.get_all_releases = MagicMock(return_value=LastReleases)
    ClearingObj.sw360.get_release = MagicMock(return_value=ReleaseData)

    recent_release_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    for r in LastReleases:
        r["createdOn"] = recent_release_date

    ClearingObj.get_last_releases()

    assert ClearingObj.project is not None
    assert ClearingObj.project.name.startswith("Last releases")
    assert len(ClearingObj.project.linked_releases) == len(LastReleases)


def test_last_releases_older_than_three_months(
    ClearingObj: Clearing, LastReleases: list, ReleaseData: dict
):
    ClearingObj.project = None

    ClearingObj.sw360.get_all_releases = MagicMock(return_value=LastReleases)
    ClearingObj.sw360.get_release = MagicMock(return_value=ReleaseData)

    old_release_date = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")
    ReleaseData["createdOn"] = old_release_date

    ClearingObj.get_last_releases()

    assert ClearingObj.project is not None
    assert ClearingObj.project.name.startswith("Last releases")
    assert len(ClearingObj.project.linked_releases) == 0


def test_get_releases_handles_none_release_data(
    ClearingObj: Clearing, LastReleases: list
):
    ClearingObj.project = ReleasesProject()
    ClearingObj.get_release_data = MagicMock(return_value=None)
    ClearingObj.is_oss_component = MagicMock(return_value=True)
    ClearingObj.project.linked_releases = []

    ClearingObj.get_releases(LastReleases)

    assert len(ClearingObj.project.linked_releases) == 0
