# Starter Kit Changelog

## Unreleased

- Preserve classical register width and measurement assignment order across all
  three backends; later measurements now overwrite earlier values, including zero.
- Reject malformed QASM headers, declarations, measurement indices, repeated gate
  operands, nonfinite parameters, and unsupported gates after measurement.
- Speed up sampling by projecting distinct basis outcomes once; correct sampling
  at zero-probability cumulative-distribution boundaries.
- Compile long classical expressions with reusable scratch registers; handle
  comments and signed operands, validate classical bit bounds and trailing tokens,
  and normalize multi-register quantum operations without duplicate measurements.
- Fix runtime web model configuration and validate JSON objects, field types,
  integer shots, request content types, and invalid HTTP body lengths.
- Reset quantum state when loading a RISC-V program and reject self-controlled CNOTs.
- Reject nonfinite LLM timeouts and accept GitHub archive root directories during
  submission collection without permitting root-level files or unsafe paths.
- Add deterministic regressions and run the complete local validation suite in CI
  on Python 3.10 and 3.14. See `../VALIDATION.md` for results and limitations.
- Seed the circuit verifier's sampling to prevent intermittent CI failures and
  calculate fidelity safely when unexpected output states occur.
- Use the importable `starter_kit/` name for the submission root.
- Add `__init__.py` so tests can use `from starter_kit import adapter` directly.

## 1.1.0 - 2026-07-27

- Publish the environment-only OpenAI-compatible L2 runtime contract.
- Fix the formal L2 scoring model to DeepSeek `deepseek-v4-flash`.
- Publish per-case call, token, and timeout budgets in `l2_policy.json`.
- Add a dependency-free `llm_client.py` transport helper without prompts or scoring logic.
- Clarify that the organizer provides no API endpoint, key, or credit before formal scoring.

## 1.0.1 - 2026-07-27

- Add the read-only local final-submission preflight.
- Define `starter_kit/` as the build and evaluation root in official forks.
- Document commit-SHA submission, server-side cutoff time, receipts, and resubmission rules.

## 1.0.0 - 2026-07-11

- Freeze submission contract v1.0.
- Add `submission.yaml`, version metadata, and machine-readable public reports.
- Remove mock scoring paths, prompt-specific answers, and the L3 reference solution.
- Clarify that formal scoring runs in an organizer-owned isolated environment.
