"""The reviewed migration-scoreboard numbers, stated once.

Every value here changes when (and only when) a core is onboarded or a legacy
workflow is retired, and the whole point of keeping them literal is that such a
change must be a reviewed edit -- the downward march of the masked/info-only
counts is the migration's scoreboard. Before this file they were scattered
across three test files and every onboarding hunted them by running the suite;
now an onboarding edits exactly this file.
"""

# manifests/core-builds.json
CATALOG_CORE_COUNT = 100

# .github/workflows audit (core_pipeline.audit_workflows)
CORE_WORKFLOW_COUNT = 100
UNMIGRATED_WORKFLOW_COUNT = 0
MASKED_BUILD_FAILURE_PATHS = 0
INFO_ONLY_RISK_WORKFLOWS = 0

# contracts/registry.py (direct-cmake/direct-make cores carry no entry)
CORE_LOG_CONTRACT_COUNT = 89
