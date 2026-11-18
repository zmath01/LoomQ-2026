# Correctness and sampling review

Reviewed against commit `80c456562330d7b41efc08f5ceba339e2dbcddda`.
Local verification used CPython 3.14.4 with the standard library only.

## Correctness fixes

- Preserve the declared classical width for explicit measurements, even when
  fewer classical bits than qubits exist. Preserve measurement source order and
  implement last-write-wins assignment, including overwriting a one with zero.
  This follows [OpenQASM measurement assignment semantics](https://openqasm.com/language/insts.html).
- Reject invalid QASM before execution: incorrect or repeated headers, missing
  terminal semicolons, unknown includes, duplicate or empty registers, invalid
  measurement indices, repeated operands in multi-qubit gates, and nonfinite or
  non-real parameters. Check measurement indices within their named registers
  before applying register offsets.
- The reference IR represents gates followed by terminal measurements. Gates
  after a measurement now raise a clear error instead of silently moving ahead
  of that measurement. Mid-circuit measurement remains outside this dialect.
- Use reusable temporaries for arbitrarily long left-associative sums and
  differences. Fix comments containing braces or `classical`, signed operands,
  whitespace in `c [ k ]`, trailing classical tokens, and duplicated whole-register
  measurements. Canonical quantum operations use flattened `q` and `c` indices.
- Classical measurement inputs are limited to declared bits `c[0]` through
  `c[16]`, mapped to `x10` through `x26`; `x27` through `x31` are compiler
  temporaries. Reject overlapping or undeclared inputs instead of corrupting them.
- Fix `/api/agent-key` calling an undefined function. Validate all configuration
  fields before updating environment variables. Reject non-object JSON bodies,
  non-JSON content types, boolean or fractional shot counts, and malformed body
  lengths; close invalid HTTP streams explicitly.
- Clear quantum state when loading a new RISC-V program and reject a CNOT whose
  control equals its target. Reject infinite and NaN model request timeouts.
- Accept the root directory entry in normal GitHub tarballs. Continue rejecting
  root-level files, links, path traversal, duplicate paths, and oversized data.

## Verification

Run from the repository root:

```sh
python3 -m compileall -q competition starter_kit tests
python3 -m unittest discover -s tests -v
python3 starter_kit/selftest.py
python3 starter_kit/tools/verify_circuits.py
python3 starter_kit/evaluator.py --level l1 --target spinq,originq,braket
python3 starter_kit/evaluator.py --level l3
python3 starter_kit/test_quantum_riscv.py
python3 starter_kit/test_l2_plumbing.py
python3 starter_kit/test_web_api.py --spawn
python3 starter_kit/check_secrets.py --history
git diff --check
```

The 53 unit tests include 27 new regression tests. The randomized arithmetic
regression checks 100 programs with long sums, differences, and self-references
under all four two-bit measurement injections, against an independent arithmetic
evaluation. The existing extended self-test also checks 25 randomized hybrid
programs with branches under every measurement injection.

All three target emitters preserve complex amplitudes for a seeded 80-gate
circuit within `1e-12` absolute error. QFT-4 agrees with the independent DFT matrix
for all 16 basis inputs: worst amplitude error `3.91e-15`, below the existing
`1e-9` threshold. The web integration suite passes all 27 checks. L1 passes all
six public cases; L3 passes its public branch case. Quantum RISC-V, local L2
transport, compilation, and secret scanning pass.

The circuit verification script uses fixed sampling seeds, removing intermittent
failures from unseeded GHZ sampling at its stricter fidelity threshold. Its
fidelity helper also handles unexpected output states as errors in distribution
instead of raising a `KeyError`.

CI runs these dependency-free functional checks on Python 3.10 and 3.14.
Real cloud hardware, paid model calls, optional vendor SDKs, and the optional
Qiskit diagram renderer were not exercised locally. L2 transport tests use a
local HTTP model stub. No real-machine evidence was generated or modified.

## Sampling performance

The sampler now aggregates integer basis outcomes before formatting classical
keys. It also avoids a separate probability list and uses the actual state norm
when sampling to tolerate floating-point drift. Right-biased binary search skips
zero-probability plateaus, including when the random draw is exactly zero.

Median of seven local runs per implementation; both versions used identical
circuits and `random.Random(42)`. Every measured workload produced identical
seeded counts before and after the change. Timings include state preparation.

| Hadamard-prepared qubits | Measured bits | Shots | Before | After | Speedup |
|---|---|---|---|---|---|
| 2 | 2 | 8,192 | 8.32 ms | 2.48 ms | 3.35x |
| 10 | 3 | 100,000 | 87.67 ms | 44.87 ms | 1.95x |
| 10 | 10 | 100,000 | 140.40 ms | 45.49 ms | 3.09x |

These measurements describe the listed local workloads, not a universal speedup.
To reproduce, load `simulate_counts` from the baseline commit and the working
tree, prepare `n` qubits with one Hadamard each, measure qubits `0..m-1` into
classical bits `0..m-1`, and time seven calls with a fresh `random.Random(42)`
per call. Compare the counts exactly and take `statistics.median` of
`time.perf_counter()` durations. The baseline simulator can be loaded without
changing the checkout using `git show 80c4565:starter_kit/loomq_core/simulator.py`
and a temporary module whose package is `starter_kit.loomq_core`.
