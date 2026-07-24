"""Identity-free catalog validation shared by Snes9x 2005 contracts."""

from __future__ import annotations

_BASE_BUILD_KEYS = frozenset(
    {
        "artifact_name",
        "driver",
        "git_version",
        "output_path",
        "source_dir",
        "source_key",
    }
)


def native_git_version_spec_is_well_formed(
    spec: object, identity: object
) -> bool:
    """Validate one exact native-version catalog identity."""

    if (
        not isinstance(spec, dict)
        or not isinstance(identity, dict)
        or set(spec)
        != {"workflow", "source", "build", "metadata", "targets"}
    ):
        return False
    source = spec.get("source")
    build = spec.get("build")
    metadata = spec.get("metadata")
    expected_build_keys = _BASE_BUILD_KEYS
    if identity.get("make_variables") is not None:
        expected_build_keys = expected_build_keys | {"make_variables"}
    expected_git_version = {
        "derivation": "native-space-short7-v1",
        "value": f" {identity['source_commit'][:7]}",
        "compiler_scope": identity["compiler_scope"],
    }
    return bool(
        isinstance(source, dict)
        and set(source) == {"url", "requested_ref", "commit", "tree"}
        and isinstance(build, dict)
        and set(build) == expected_build_keys
        and isinstance(metadata, dict)
        and set(metadata) == {"source_path", "artifact_name"}
        and spec.get("workflow") == identity["workflow"]
        and source.get("url") == identity["source_url"]
        and source.get("requested_ref") == identity["source_requested_ref"]
        and source.get("commit") == identity["source_commit"]
        and source.get("tree") == identity["source_tree"]
        and build.get("driver") == "libretro-super"
        and build.get("source_key") == identity["source_key"]
        and build.get("source_dir") == identity["source_dir"]
        and build.get("output_path") == identity["output_path"]
        and build.get("artifact_name") == identity["artifact_name"]
        and build.get("git_version") == expected_git_version
        and (
            identity.get("make_variables") is None
            or build.get("make_variables") == identity["make_variables"]
        )
        and metadata.get("source_path") == identity["metadata_source_path"]
        and metadata.get("artifact_name")
        == identity["metadata_artifact_name"]
        and spec.get("targets") == identity["targets"]
    )


__all__ = [
    "native_git_version_spec_is_well_formed",
]
