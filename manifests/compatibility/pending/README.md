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

Atari800, FBNeo, MAME 2003-Plus, and PicoDrive currently use this transition
state while their exact catalog and build contracts await selected and
independent local E2E runs. Remove a pending record only in the same change that
adds its canonical compatibility evidence; future cores can use the same
non-admitting contract.
