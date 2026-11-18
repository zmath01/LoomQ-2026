# Circuit editor and GitHub Pages

Live site: https://zmath01.github.io/LoomQ-2026/

## Diagram compaction is not topology optimization

Independent operations on disjoint qubit sets commute: `(A ⊗ I)(I ⊗ B) = A ⊗ B`.
They may therefore share a drawing column, as in Qiskit's left justification.
The drawing preserves the order of operations on each qubit. It also reserves
all rows crossed by a multi-qubit connector, avoiding ambiguous intersections.
A column is not a calibrated execution time slot and does not promise that a
particular device can run those gates simultaneously.

The layout selector changes only the view. Compact mode places independent
operations together; serial mode puts each gate in its own column. Neither
mode changes the QASM, gate count, angles, logical connections, measurements,
or hardware mapping. Hardware topology optimization would require a coupling
map, physical-qubit layout and routing, often with inserted SWAPs. That is not
what this editor does. Adding a gate is a deliberate circuit edit; insertion
may reorder existing independent operations to match their displayed order.

The reference view calls the public Qiskit API directly:
`QuantumCircuit.from_qasm_str(qasm).draw(output='text', justify=mode, fold=-1, cregbundle=False)`.
No private Qiskit layout implementation is copied. The small interactive grid
implements only display scheduling and selection; it is not advertised as a
pixel-identical Qiskit drawer.

Official references: [drawing options](https://quantum.cloud.ibm.com/docs/en/api/qiskit/2.5/qiskit.visualization.circuit_drawer)
and [bit ordering](https://quantum.cloud.ibm.com/docs/en/qiskit/bit-ordering).
The uppermost wire is q[0]; count strings put c[0] on the right.

## Correctness and editing contract

`loomq_core/editor.py` reuses the existing `parse_qasm2` parser and safe parameter
evaluator. There is no second browser QASM parser. Single-line programs, named
registers, nested expressions and negative angles use the same semantics as
simulation. The grid supports at most 12 qubits, 64 classical bits and 500
operations, including measurements. Unsupported or malformed QASM produces an
explicit error instead of a partial diagram or a silently rewritten program.
Only terminal measurements and the existing gate whitelist are supported.

Switching views or changing layout never serializes the circuit. A deliberate
edit normalizes register names to q/c and expressions to round-trippable numeric
radians, preserving binary64 angle values, classical width, measurement indices
and write order. Comments and original register names are not preserved after
such an edit. The explicit “measure all” action replaces the mapping; ordinary
gate edits do not. With no explicit measurements, the simulation API defaults
to reading all qubits, as described below the grid.

SWAP uses two crosses; CX/CCX use control dots and a target symbol; CU1 uses a
control dot and P(angle), not a CNOT target. RZ's tooltip gives its exact matrix,
including global phase. QFT-4 includes final bit-reversal SWAPs. Grover-3 has
two search qubits plus an ancilla and returns the two-bit marked state `11`.
Sample histograms describe observed frequencies: a single measurement basis
cannot establish entanglement or coherence, and finite samples do not establish
an exact probability of one.

Phone layouts stack the palette, circuit and results, retain readable diagram
fonts with horizontal circuit scrolling, and support tapping gates and wires.
Multi-qubit placement explicitly selects the remaining operands. Removing a
wire is blocked while any gate uses it, including as a control. Invalid edits,
cancelled angle prompts and stale asynchronous replies do not overwrite source.

## Static deployment and local service

`.github/workflows/pages.yml` validates the code, installs Qiskit 2.5.2, builds
`site/`, and deploys the artifact with GitHub's official Pages actions. It runs
on pushes to main and manual dispatch. The repository Pages source must be
**GitHub Actions**. Generated `site/` and runtime caches are ignored by Git.

GitHub Pages cannot run the Python HTTP service. The static build loads
Pyodide 0.27.7 in a worker and imports a zip of the existing Python adapter,
parser, simulator and transpilers. Browser computations use this same core;
they are local reference simulations, not remote QPU jobs. The first visit
downloads approximately 14 MiB of runtime files from the deployed site.
No credentials or model configuration files are included in the artifact.

The five shipped circuit files have genuine Qiskit reference diagrams generated
at build time, keyed by the parsed model and layout mode. A custom circuit still
supports editing and simulation. If no matching Qiskit drawing exists, the
reference view clearly shows QASM and explains that a live standard drawing
requires the local Python service with Qiskit installed. Agent chat also requires
the local service. Neither feature is simulated by an imitation response.

Local build and preview (Python 3.10+; Node.js for layout tests):

```sh
python3 -m pip install qiskit==2.5.2
python3 -m unittest discover -s tests -v
node --test tests/editor-layout.test.cjs
python3 starter_kit/tools/verify_circuits.py
python3 starter_kit/tools/build_pages.py
python3 -m http.server 8000 --directory site
```

For the full local service: `python3 starter_kit/loomq_web.py --port 8000`.
Its integration check is `python3 starter_kit/test_web_api.py`.

Regression coverage includes negative and fractional angles, binary64 parameter
round trips, malformed input, measurement overwrites, connector intersections,
serial-mode immutability, and 30 deterministic random circuits compared before
and after display reordering on four input basis states. Complex amplitudes
agree to `1e-12`; an additional check compares the core directly with Qiskit
Statevector. Browser checks cover touch editing, cancellation, control-wire
removal, invalid-source recovery, Grover counts, Qiskit examples, and all five
screens at widths 320, 390, 768, 1024 and 1440 pixels.
