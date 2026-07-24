# Genesis Plus GX historical build-log oracles

These immutable, test-only logs preserve two valid ARM64 parallel-output
orderings and the byte-identical ARMHF ordering from the historical Genesis
Plus GX final and reproduction runs. Production lifecycle state must use fresh
core-named schema-v2 runs; the old schema-v1, repository-dirty records are never
promotion inputs.

- `arm64-final-build.txt`: SHA-256
  `1b946fc9d4e4cb700c12aab1deaa8ccb03943405b401bf19ad47db1f1e0cc93c`
- `arm64-repro-build.txt`: SHA-256
  `178dcdaa3cdca335d0c593ddb9183ad9ceb40b0f05b8473255eb53cce9634c22`
- `armhf-build.txt`: SHA-256
  `fcac51db9ea06dee58581de12c2dd1b62674ebb7f74c2d1b173415ad91ca4140`

The source is commit `fa4dca561e08d5be9077419f7b255e1da213ed21`, tree
`7f4b0916e938e15e046e1c35acd0173aab1aaac3`, with no submodules.
