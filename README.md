# Automated file exchange between SW360 & Fossology

[![Python](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/)
[![uv](https://img.shields.io/badge/dependency%20manager-uv-5f5fff.svg)](https://docs.astral.sh/uv/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE.md)
[![CI](https://github.com/fossology/fossology-workflow/actions/workflows/ci.yml/badge.svg)](https://github.com/fossology/fossology-workflow/actions/workflows/ci.yml)

> Note: This work has been mostly sponsored by [Siemens Healthineers](https://github.com/Siemens-Healthineers).

The workflow implemented in this project automatically transfers **source files** attached as linked releases in a
project on SW360 to a defined project structure on Fossology.

Once clearing results are available on Fossology, clearing reports (Unified Report and CLI formats) will automatically
be generated and **uploaded** to the corresponding linked release on SW360.

The grey box in the diagram below represents the automated workflow as implemented in this project:

```plantuml
hide footbox
actor Developer #ffb900
participant SW360
box "Fossology Workflow" #adbecb
participant "Workflow Engine" as wf
end box
participant Fossology
actor "Clearing Expert" as ce #4bb9b9
Developer -> SW360: Create new project, components, releases
activate SW360 #ffb900
Developer -> SW360: Upload OSS source files
SW360 -> wf: Retrieve source files
activate wf
wf -> Fossology: Create folder structure according\n to SW360 component names
Developer -> SW360: Issue a clearing request
deactivate SW360
SW360 --> ce: Send request to clearing team
ce -> Fossology: Start clearing
activate Fossology #4bb9b9
...
note right of Fossology #c3f0f0
    Time spend on Fossology
    to perform all the clearings
end note
...
wf <- Fossology: Retrieves reports
ce -> Fossology: Set clearing status to "closed"
deactivate Fossology
wf -> SW360: Uploads reports\nSets clearing status
deactivate wf
activate SW360 #ffb900
Developer <- SW360: Retrieves product clearing
deactivate SW360
```

## Required infrastructure and configuration

This workflow is designed to be integrated into corporate software clearing infrastructures. It bridges two Open Source platforms commonly used in Open Source compliance:

* **[SW360](https://www.eclipse.org/sw360/)**: a component management and license compliance platform used to catalog software components, track their clearing status, and store source files and clearing reports. Your organization needs a running SW360 instance with REST API access enabled, along with valid API tokens for authentication.

* **[FOSSology](https://www.fossology.org/)**: a license scanning and compliance analysis tool that performs automated and manual license clearing on uploaded source files. A dedicated FOSSology instance is required, configured with a folder structure for organizing uploads and a group for sharing clearing results across the team.

Both platforms must be reachable over the network from the environment running this workflow (e.g. a CI runner or a developer workstation). REST API tokens with appropriate read/write permissions are required for each.

The automation engine uses the REST APIs offered by SW360 and Fossology via the following Python wrapper libraries:

* **[sw360-python](https://github.com/sw360/sw360python)**: Python client for the SW360 REST API
* **[fossology-python](https://github.com/fossology/fossology-python)**: Python client for the FOSSology REST API

### Fossology folder structure

The folder structure used in Fossology to sort component by name and versions looks like this:

```sh
FOSSOLOGY_FOLDER
|
|-- component1 (from the SW360 component name)
|   |
|   |-- component1_version-1.0.0_tar.bz2 (from source attachment of the release on SW360)
|   |-- component1_version-2.0.0_tar.bz2 (using the release id as description string)
|   |-- component1_version-3.0.0_tar.bz2
|
|-- component2
|   |
|   |-- component2_version-1.0.0_tar.bz2
|   |-- component2_version-2.0.0_tar.bz2
|   |-- component2_version-3.0.0_tar.bz2
|
|-- component3
|   |
|   |-- component3_version-1.0.0_tar.bz2
|   |-- component3_version-2.0.0_tar.bz2
|   |-- component3_version-3.0.0_tar.bz2
```

The workflow relies on this layout for deterministic upload placement and efficient clearing operations:

* **Root folder (`FOSSOLOGY_FOLDER`)**:
  * This is the single entry point used by the automation.
  * All workflow-managed uploads are stored under this root so the scanner and clearing team can work in one consistent area.
* **Component folders (level 1)**:
  * Each SW360 component maps to one dedicated Fossology subfolder.
  * Grouping uploads by component keeps all versions together and avoids mixing unrelated projects.
* **Versioned source uploads (level 2)**:
  * Each SW360 release source archive is uploaded as a separate item in the component folder.
  * The release ID is stored in the upload description to keep a stable link back to SW360, even if names are similar.

This organization has two important benefits:

* **Reuse of prior clearing work**: when a new version is added to an existing component folder, previous versions are easy to discover and compare, which improves matching and reuse decisions.
* **Operational traceability**: auditors and clearing experts can quickly navigate from component -> version -> report context, and correlate entries with SW360 records.

Practical recommendations when preparing `FOSSOLOGY_FOLDER`:

* Use a dedicated folder that is managed only by this workflow (do not mix manual uploads there).
* Keep component naming stable in SW360; frequent renames create fragmented folder histories and reduce reuse effectiveness.
* Ensure the configured `FOSSOLOGY_GROUP` has permissions for all folders and uploads created under the root.

### Environment variables

To specify the environment used for the automated workflow, following variables are required:

#### Required

All six variables below must be set — the application exits immediately if any is missing.

| Variable | Description |
|----------|-------------|
| `SW360_URL` | Base URL of the SW360 instance |
| `SW360_TOKEN` | REST API access token for SW360 |
| `FOSSOLOGY_URL` | Base URL of the Fossology instance |
| `FOSSOLOGY_TOKEN` | REST API access token for Fossology |
| `FOSSOLOGY_FOLDER` | ID of the root Fossology folder for source uploads |
| `FOSSOLOGY_GROUP` | Fossology group name for sharing clearing results |

#### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `SW360_PROJECT` | — | SW360 project ID (required for `request-clearing` if `SW360_CR` is not set) |
| `SW360_CR` | — | SW360 clearing request ID, e.g. `CR-233` (preferred for `request-clearing`) |
| `UPLOADS_TO_FOSSOLOGY` | `false` | Upload source files from SW360 to Fossology |
| `REPORTS_TO_SW360` | `false` | Generate and upload clearing reports back to SW360 |
| `UPLOAD_INITIAL_SCAN_REPORT` | `false` | Upload initial scan reports (SPDX v2 format) for new releases |
| `REUSE` | `false` | Reuse previous clearing results when a matching upload is found |
| `BATCH_SIZE` | `20` | Maximum number of source files uploaded per run |
| `FOSS_REPORT_WAITING_TIME` | `10` | Retry delay in seconds when waiting for report generation |

#### Specific clearing flags

These flags are **release-level SW360 configurations**.

Set them in each release's `additionalData` map in SW360 (not as standalone workflow toggles). The workflow reads those `additionalData` keys during source selection and upload decisions.

| SW360 `additionalData` key | Value | Workflow behavior |
|---------------------------|-------|-------------------|
| `WF:ignore` | empty or any value | Skip the release (`Upload status: IGNORED`). |
| `WF:force_reclearing` | empty or any value | Upload source even when clearing reports already exist in SW360. |
| `WF:use_source` | attachment filename, e.g. `component-1.2.3.tar.gz` | Prefer this source file when multiple source attachments exist. |

Default keys interpreted by the code are:

* `WF:ignore`
* `WF:force_reclearing`
* `WF:use_source`

You can override these key names through environment variables if your SW360 instance uses different conventions:

```bash
export IGNORE_FLAG="WF:ignore"
export FORCE_RECLEARING_FLAG="WF:force_reclearing"
export USE_SOURCE_FLAG="WF:use_source"
```

## Running the Workflow

The workflow provides two commands:

### Clear a specific project using `request-clearing`

Requires **one of** `SW360_PROJECT` or `SW360_CR` in the environment.

```bash
export SW360_URL="https://sw360.example.com"
export SW360_TOKEN="your-sw360-token"
export FOSSOLOGY_URL="https://fossology.example.com"
export FOSSOLOGY_TOKEN="your-fossology-token"
export FOSSOLOGY_FOLDER="3"
export FOSSOLOGY_GROUP="clearing-team"

# Identify the project by clearing request (preferred)
export SW360_CR="CR-233"

# Enable uploads and report generation
export UPLOADS_TO_FOSSOLOGY="true"
export REPORTS_TO_SW360="true"

uv run python fossology_workflow request-clearing
```

### Batch ISR generation using `create-initial-reports`

Generates initial scan reports for the latest releases uploaded to SW360. Does not require `SW360_PROJECT` or `SW360_CR`.

```bash
uv run python fossology_workflow create-initial-reports
```

> This workflow is typically scheduled every night to shorten the round-trip times between new available releases in SW360 and automatically generated initial clearing reports.

### Workflow phases

Both commands execute the same pipeline:

1. **Upload sources**: download source attachments from SW360 releases, upload them to Fossology with folder structure matching component names
2. **Generate reports**: wait for Fossology scanning agents to finish, then generate Unified Report and CLI XML reports
3. **Upload reports**: upload generated reports back to the corresponding SW360 releases (if `REPORTS_TO_SW360=true`)
4. **Produce summary**: write a CSV file and log metrics summarizing the workflow results

## Installation

A packaged version of the script is published in this project. To install via **uv**, use the following configuration in your `pyproject.toml`:

```toml
[project]
dependencies = [
    "fossology-workflow>=1.5.3",
]
```

Alternatively, if you are cloning the repository and want to run the workflow directly:

```bash
git clone git@github.com:fossology/fossology-workflow.git
cd fossology-workflow
uv sync
```

After installing, configure the required environment variables before running any command:

```sh
export FOSSOLOGY_URL="https://fossology.org.com"
export FOSSOLOGY_TOKEN="XXXX..."
export SW360_URL="https://sw360.org.com"
export SW360_TOKEN="XXXX..." # Note that you'll need a RW token to upload data back to sw360
export FOSSOLOGY_FOLDER="Folder-id"
export FOSSOLOGY_GROUP="Group-name"
```

> Refer to the [Environment variables](#environment-variables) section for complete details about all required and optional variables.

Then execute either of the commands described in [Running the Workflow](#running-the-workflow).


### Generated artifacts

The workflow generates the following artifacts after each run:

| Pattern | Content |
|---------|---------|
| `automated-workflow-*.log` | Timestamped workflow log with detailed execution trace |
| `workflow-summary-*.csv` | CSV summary of results per release (see below for field descriptions) |
| `*.docx` | Generated Unified Reports (one per cleared release) |
| `*.xml` | Generated CLI XML reports (one per cleared release) |

#### Workflow summary CSV

The CSV file named `workflow-summary-{project-name}.csv` provides a snapshot of the clearing state for all releases processed in a SW360 project. Each row represents one release and documents:

* Where the source originates (SW360 release metadata)
* What happened during the upload phase (success, skip reason, etc.)
* Whether clearing reports were generated and uploaded
* How much clearing effort remains (file count still pending review)
* A direct link to the upload in Fossology for manual inspection

Use this CSV to:

* **Track progress**: see which releases are cleared, pending, or skipped
* **Identify problems**: quickly spot errors (SW360_ERROR, FOSSOLOGY_ERROR) by status columns
* **Estimate effort**: understand remaining work via the Complexity and pending file counts
* **Guide reuse**: check Reuse Info to find candidate components with prior cleared work
* **Share results**: export to team members or compliance tracking systems

The following sections explain each column and status value:

#### Columns

| Column | Description |
|--------|-------------|
| **Project** | SW360 project name |
| **Subject** | Release identifier formatted as `{component-name} {version}` to uniquely identify the release in SW360 |
| **Clearing Status** | Current clearing state in SW360: `NEW_CLEARING` (not yet reviewed), `APPROVED` (approved by compliance), `REPORT_AVAILABLE` (clearing report attached), or `SCAN_AVAILABLE` (automated scan finished). Shows whether clearing was already completed before this workflow run. |
| **Fossology Status** | Current upload clearing status in Fossology: `Open` (awaiting review), `InProgress` (review in progress), `Closed` (review complete, cleared), or `Rejected` (failed to clear). Reflects the state of the corresponding upload in the Fossology instance. |
| **Upload status** | Result of the upload phase (see upload status values below) — indicates whether the source was successfully uploaded, skipped, already present, or encountered an error |
| **Report status** | Result of the report generation and upload phase: a status name like `UPLOADED`, or an integer representing the **number of files still pending clearance**. If all files are cleared, reports are generated and uploaded automatically. |
| **Complexity** | Estimated clearing effort level based on file count in the upload (see complexity table below). Provides a quick gauge of how much manual work remains. |
| **Fossology Url** | Direct clickable link to the upload in the Fossology web UI, useful for inspecting details, manually clearing files, or reviewing license decisions |
| **Reuse Info** | Shows candidate component information if `REUSE=true` and a reusable prior version was found; otherwise suggests enabling `REUSE` to benefit from prior clearing work on similar versions |

#### Upload status values

| Status | Meaning | Next steps |
|--------|---------|-----------|
| `UPLOADED` | Source successfully uploaded to Fossology and scanning agents scheduled | Wait for scanning to complete; workflow will retrieve and upload reports when ready |
| `EXISTS` | Source already present in Fossology (matching filename and release ID) | Source is ready for clearing; check Fossology Status and Report Status for details |
| `CLEARED` | A clearing report (CLEARING_REPORT or COMPONENT_LICENSE_INFO_XML) already attached in SW360 | Clearing already complete; use force-reclearing flag `WF:force_reclearing` if re-clearing is needed |
| `PENDING` | Not yet analyzed in this workflow run (deferred because batch size was reached) | Run the workflow again to process remaining sources; use `BATCH_SIZE` or disable limit to process all at once |
| `NOT_OSS` | Component type in SW360 is neither `OSS` nor `CODE_SNIPPET`, thus not applicable for clearing | Review component type classification; change type if clearing is required |
| `NO_SOURCE` | No source attachment found in SW360 for this release | Upload a source file (SRS or SOURCE_*) to the release in SW360 |
| `MULTIPLE_SOURCE` | Multiple source attachments found and ambiguous (unclear which to use) | Use the `WF:use_source` flag on the release to specify the preferred source filename |
| `IGNORED` | Release skipped due to `WF:ignore` flag in release additionalData | Remove the flag if clearing is needed |
| `DO_NOT_UPLOAD` | Source found but not uploaded per workflow configuration (`UPLOADS_TO_FOSSOLOGY=false`) | Enable uploads via `UPLOADS_TO_FOSSOLOGY=true` to proceed |
| `JOBS_SCHEDULED` | Upload already existed in Fossology but scanning jobs were missing; jobs have been re-scheduled | Wait for scanning agents to complete; workflow will retrieve reports when ready |
| `EMPTY` | Upload to Fossology failed: returned empty or corrupted | Check logs for upload errors; retry or manually upload |
| `CORRUPT` | SHA1 checksum mismatch between SW360 source and Fossology upload: data integrity issue | Download the source again from SW360, verify integrity, and re-upload |
| `SW360_ERROR` | Error retrieving release data from SW360 (network, permission, or API issue) | Check SW360 connectivity, token validity, and release accessibility |
| `UNSCHEDULED` | Upload succeeded but error while scheduling scanning jobs in Fossology | Check Fossology connectivity and job configuration; retry or manually trigger agents |

#### Report status values

| Status | Meaning | Next steps |
|--------|---------|-----------|
| `UPLOADED` | Reports successfully generated from Fossology and uploaded to SW360 | Clearing complete for this release; review reports in SW360 |
| `SW360_ERROR` | Error uploading generated reports to SW360 (network, permission, or API issue) | Check SW360 connectivity and token permissions; retry workflow |
| `FOSSOLOGY_ERROR` | Error generating or downloading reports from Fossology (timeout, API failure) | Check Fossology status and job history; retry or manually generate reports |
| *(number)* | Integer value indicating the **number of files still pending clearance** in Fossology, no report generated yet | Wait for clearing team to finish reviewing remaining files; rerun workflow to retrieve final reports when done |

#### Complexity and effort estimation

The **Complexity** column and the final summary row use this mapping to estimate the manual clearing effort needed:

| Complexity | File count range | Estimated effort (person-hours) | Context |
|------------|-----------------|--------------------------------|---------|
| `VERY_SMALL` | 0 - 100 | 0.5 | Quick review; few license questions |
| `SMALL` | 101 - 1,000 | 2 | Standard effort; manageable in one session |
| `MEDIUM` | 1,001 - 5,000 | 5 | Significant work; plan for multiple review passes |
| `LARGE` | 5,001 - 10,000 | 12 | Major effort; coordinate with clearing team, allow 1–2 days |
| `VERY_LARGE` | 10,000+ | 20 | Large project; schedule extensive review period, may require specialists |

**How the estimate is calculated:**

The last row of the CSV (`Total effort`) aggregates effort across all releases with pending files. For example, if you have:

* Release A: 500 files pending → SMALL complexity (2 hours)
* Release B: 3,000 files pending → MEDIUM complexity (5 hours)  
* Release C: UPLOADED (0 files pending) → no effort

Then the **Total effort** row shows **7 hours**.

**How to use this data:**

* **Planning**: allocate clearing team capacity based on total effort estimate
* **Prioritization**: address `VERY_SMALL` and `SMALL releases first for quick wins
* **Forecasting**: report to management how long full compliance will take
* **Monitoring**: rerun the workflow periodically to see effort remaining (should decrease as files are cleared)

## Contribution Guidelines

This section focuses on what developers need locally and which checks are enforced by GitHub Actions.

### Development environment

To contribute to this project, install:

* **Python**: version **3.13**
* **[uv](https://docs.astral.sh/uv/)**: version **>= 0.7**

Install dependencies:

```bash
uv sync
```

### GitHub Actions quality checks

The CI workflow in [ci.yml](.github/workflows/ci.yml) runs on:

* Pushes to `main`
* Pull requests targeting `main`

It executes two jobs:

1. **`lint`**
   * `uv run ruff check --select I .` (import sorting check)
   * `uv run ruff format --check` (formatting check)
2. **`test`**
   * `uv run pytest -c pytest-ci.ini`
   * Uploads `htmlcov/` and `junit.xml` as CI artifacts

To keep CI green before pushing, run the same checks locally:

```bash
# Match CI lint checks
uv run ruff check --select I .
uv run ruff format --check

# Match CI test command
uv run pytest -c pytest-ci.ini
```

If import ordering issues are reported, you can auto-fix locally with:

```bash
uv run ruff check --select I --fix .
```

For running the workflow automation itself, see [Installation](#installation).
