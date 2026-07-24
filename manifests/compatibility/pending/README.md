# Pending compatibility evidence

Each JSON file in this directory marks one cataloged core whose exact build
contract has been committed so clean local E2E evidence can be created, but
whose selected and independent reproduction runs do not yet support canonical
compatibility admission.

Pending records are publication-disabled transition state. They are never
loaded as `manifests/compatibility/<core>.json`, never appear in
`golden_sources`, and are not valid pin, release, or channel inputs. A lifecycle
completion removes `<core>.json` from this directory in the same change that
adds its canonical top-level compatibility record.

Do not use a pending record to represent a failed, unsupported, or compatible
core. Preserve those claims in their owning evidence and policy surfaces.

This directory is empty when every cataloged core is canonical (the
state since 2026-07-24). Remove a pending record only in the same change
that adds its canonical compatibility evidence; future cores use the
same non-admitting transition contract during onboarding.
