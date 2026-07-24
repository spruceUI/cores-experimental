# Genesis Plus GX Wide historical build-log oracles

These immutable, test-only logs preserve two valid ARM64 parallel-output
orderings and the byte-identical ARMHF ordering from the historical Genesis
Plus GX Wide final and reproduction runs. Production lifecycle state must use
fresh core-named schema-v2 runs; the old schema-v1, repository-dirty records
are never promotion inputs.

- `arm64-final-build.txt`: SHA-256
  `8b37e8dd6bf072cb75a19d8cb243406b3fa798e0515976fd9d9c537ee9fffc8d`
- `arm64-repro-build.txt`: SHA-256
  `86e233f0ab64f00d5985ffdbea2b990d15ef47e60e6fed0ee91d06820744dd60`
- `armhf-build.txt`: SHA-256
  `9d52149408262de1a3b22b549ecc07b9283ce7c1968e728c2188927ea39551f4`

The source is commit `29d9d104338f46bc2e65438fb207bcf54f701e92`, tree
`27e05ed457d9c10e51b6c69067e1c05599df08fb`, with no submodules.
