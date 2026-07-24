# CrocoDS historical build-log oracles

These immutable, test-only logs preserve two valid ARM64 parallel-output
orderings and the byte-identical ARMHF ordering from the historical CrocoDS
hardened final/reproduction runs. Production lifecycle state must use fresh
core-named schema-v2 runs; these files are only contract regression inputs.

- `arm64-final-build.txt`: SHA-256
  `df936492192a8393f9c6e701fe55685a7aa48b05a2f05a580c6c87f87db03b03`
- `arm64-repro-build.txt`: SHA-256
  `1299926e041ead6934ab42101573072093e2c49c9045b4c1a626e8f590fb0d60`
- `armhf-build.txt`: SHA-256
  `05c5c87eedb63795e408c68da023507c71edf1d94811643bcac33133272708d3`

The source is commit `87bbb3d9007ac537864278c6c3149ae3291873f8`, tree
`5a76585f521954c8e8ebef9b489a4d6c7a8b73db`, with no submodules.
