# Copyright (c) Siemens 2020
# SPDX-License-Identifier: MIT

from fossology_workflow.clearing import normalize_release_name, normalize_report_name


def test_normalize_delete_char_works():
    release_name = "django-extensions\x7f"
    assert normalize_release_name(release_name) == "django-extensions"

    release_name = "django-extensions\x7f"
    assert normalize_release_name(release_name) == "django-extensions"


def test_normalize_report_names():
    report_name = "CLIXML_zone.js-0.11.8.tgz_2022-08-26_19:06:11.xml"
    report_name = normalize_report_name(report_name)
    assert report_name == "CLIXML_zone.js-0.11.8.tgz_2022-08-26_19_06_11.xml"
