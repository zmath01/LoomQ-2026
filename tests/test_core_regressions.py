"""Deterministic regressions for circuit semantics and hybrid compilation."""

import math
import random
import unittest
from unittest import mock

from starter_kit import adapter
from starter_kit.loomq_core.qasm import Circuit, Gate, parse_qasm2
from starter_kit.loomq_core.simulator import simulate_counts, statevector
from starter_kit.loomq_core.transpilers import parse_target_ir
from starter_kit.riscv_emulator import TinyRISCVEmulator
from starter_kit.riscv_emulator_ext import QuantumRISCVEmulator


def program(body, qubits=2, clbits=2):
    return ('OPENQASM 2.0; include "qelib1.inc"; '
            f'qreg q[{qubits}]; creg c[{clbits}]; {body}')


class CircuitRegressionTests(unittest.TestCase):
    def test_circuit_verifier_reports_unexpected_states_without_crashing(self):
        from starter_kit.tools.verify_circuits import fidelity

        self.assertEqual(fidelity({"01": 8}, {"00": 1.0}, 8), 0.0)

    def test_partial_measurement_preserves_classical_width(self):
        source = program("x q[1]; measure q[1] -> c[0];", clbits=1)
        for target in adapter.SUPPORTED_TARGETS:
            with self.subTest(target=target):
                self.assertEqual(adapter.run(source, target, 8)["counts"], {"1": 8})

    def test_measurements_overwrite_in_source_order_including_zero(self):
        for measurements in (
            "measure q[1] -> c[0]; measure q[0] -> c[0];",
            "measure q[0] -> c[0]; measure q[1] -> c[0];",
        ):
            source = program("x q[0]; " + measurements, clbits=1)
            expected = {"1" if measurements.startswith("measure q[1]") else "0": 8}
            self.assertEqual(simulate_counts(parse_qasm2(source), 8), expected)
            for target in adapter.SUPPORTED_TARGETS:
                with self.subTest(target=target, measurements=measurements):
                    self.assertEqual(adapter.run(source, target, 8)["counts"], expected)

    def test_zero_rng_does_not_select_zero_probability_state(self):
        circuit = parse_qasm2(program("x q[0]; measure q -> c;"))
        rng = mock.Mock()
        rng.random.return_value = 0.0
        self.assertEqual(simulate_counts(circuit, 3, rng), {"01": 3})

    def test_invalid_shots_are_rejected_consistently(self):
        source = program("measure q -> c;")
        for shots in (True, False, 0, -1, 1.5, "2", None):
            with self.subTest(shots=shots):
                with self.assertRaises(ValueError):
                    simulate_counts(parse_qasm2(source), shots)
                with self.assertRaises(ValueError):
                    adapter.run(source, "spinq", shots)

    def test_invalid_qasm_is_rejected_before_execution(self):
        invalid = [
            program("measure q[2] -> c[0];"),
            program("measure q[0] -> c[2];"),
            program("qreg q[1];"),
            program("creg q[1];"),
            program("qreg other[0];"),
            program("creg other[0];"),
            program("cx q[0], q[0];"),
            program("ccx q[0], q[1], q[1];"),
            program("h q[0]"),
            program("measure q[0] -> c[0]; x q[0];"),
            program("ry(1e309) q[0];"),
            program("ry((-1)**0.5) q[0];"),
            program("ry(True) q[0];"),
            program("ry(1/0) q[0];"),
            program("ry(pi,) q[0];"),
            program("h q[0];").replace("OPENQASM 2.0", "OPENQASM 12.0"),
            program("h q[0];") + "OPENQASM 2.0;",
            program("h q[0];").replace('"qelib1.inc"', '"unknown.inc"'),
            "qreg q[1]; OPENQASM 2.0;",
            "// OPENQASM 2.0\nqreg q[1];",
            # Local index overflow must not alias the next register.
            "OPENQASM 2.0; qreg a[1]; qreg b[1]; creg c[2]; measure a[1] -> c[0];",
        ]
        for source in invalid:
            with self.subTest(source=source), self.assertRaises(ValueError):
                parse_qasm2(source)

    def test_multiple_registers_keep_offsets_and_bit_order(self):
        source = ("OPENQASM 2.0; qreg a[1]; qreg b[2]; creg first[1]; creg second[2]; "
                  "x b[1]; measure a -> first; measure b -> second;")
        for target in adapter.SUPPORTED_TARGETS:
            self.assertEqual(adapter.run(source, target, 8)["counts"], {"100": 8})

    def test_all_gates_preserve_complex_amplitudes_across_targets(self):
        # Compare amplitudes, rather than sampled probabilities, so phase errors
        # in controlled-gate lowering cannot hide behind measurement.
        rng = random.Random(20261118)
        gates = []
        for _ in range(80):
            name = rng.choice(("h", "x", "s", "sdg", "t", "tdg", "ry", "rz", "cx", "cu1", "swap", "ccx"))
            arity = 3 if name == "ccx" else 2 if name in ("cx", "cu1", "swap") else 1
            params = (rng.uniform(-2 * math.pi, 2 * math.pi),) if name in ("ry", "rz", "cu1") else ()
            gates.append(Gate(name, params, tuple(rng.sample(range(4), arity))))
        circuit = Circuit(4, 4, gates)
        from starter_kit.loomq_core.transpilers import transpile_circuit

        expected = statevector(circuit)
        for target in adapter.SUPPORTED_TARGETS:
            actual = statevector(parse_target_ir(target, transpile_circuit(circuit, target)))
            self.assertLess(max(abs(a - b) for a, b in zip(actual, expected)), 1e-12)


class QuantumEmulatorRegressionTests(unittest.TestCase):
    def test_loading_a_program_resets_quantum_state(self):
        emulator = QuantumRISCVEmulator()
        emulator.load_program("li x1, 1\nqinit x1\nqx x0")
        emulator.execute()
        emulator.load_program("qprob x2, x0")
        with self.assertRaises(RuntimeError):
            emulator.execute()

    def test_qcx_rejects_identical_control_and_target(self):
        emulator = QuantumRISCVEmulator()
        emulator.load_program("li x1, 1\nqinit x1\nqcx x0, x0")
        with self.assertRaises(ValueError):
            emulator.execute()


class HybridRegressionTests(unittest.TestCase):
    def execute(self, body, injection=1):
        _, assembly = adapter.compile_hybrid(program("measure q -> c;") + "classical {" + body + "}")
        emulator = TinyRISCVEmulator()
        emulator.load_program(assembly)
        emulator.set_register("x10", injection)
        return emulator.execute()

    def test_long_expressions_and_self_references(self):
        result = self.execute("r1 = 3; r1 = c[0] + r1 - 2 + 4 - 5 + 6 + 7 - 8 + 9;")
        self.assertEqual(result["x1"], 15)

    def test_long_comparisons_preserve_both_operands(self):
        expression = "c[0] + 1 + 2 + 3 + 4 - 5 + 6 - 7"
        for injection in (0, 1):
            result = self.execute(f"if ({expression} == 1 + 2 + 3 + 4 - 5 + 6 - 7) {{r1 = 9;}} else {{r1 = 8;}}", injection)
            self.assertEqual(result["x1"], 9 if injection == 0 else 8)

    def test_randomized_long_expressions_match_independent_arithmetic(self):
        rng = random.Random(20261118)
        for case in range(100):
            statements = []
            for _ in range(12):
                target = rng.randint(1, 9)
                terms = [rng.choice([str(rng.randint(-20, 20)),
                                     "r%d" % rng.randint(1, 9), "c[0]", "c[1]"])
                         for _ in range(rng.randint(1, 20))]
                operators = [rng.choice(("+", "-")) for _ in terms[1:]]
                statements.append((target, terms, operators))
            body = " ".join(
                "r%d = %s%s;" % (target, terms[0], "".join(
                    " %s %s" % pair for pair in zip(operators, terms[1:])))
                for target, terms, operators in statements
            )
            _, assembly = adapter.compile_hybrid(program("measure q -> c;") + "classical {" + body + "}")
            for injection in range(4):
                expected = {"r%d" % i: 0 for i in range(1, 10)}
                bits = {"c[0]": injection & 1, "c[1]": injection >> 1}

                def value(token):
                    return expected[token] if token in expected else bits[token] if token in bits else int(token)

                for target, terms, operators in statements:
                    result = value(terms[0])
                    for operator, term in zip(operators, terms[1:]):
                        result += value(term) if operator == "+" else -value(term)
                    expected["r%d" % target] = result
                emulator = TinyRISCVEmulator()
                emulator.load_program(assembly)
                emulator.set_register("x10", bits["c[0]"])
                emulator.set_register("x11", bits["c[1]"])
                actual = emulator.execute()
                with self.subTest(case=case, injection=injection):
                    self.assertEqual([actual.get("x%d" % i, 0) for i in range(1, 10)],
                                     [expected["r%d" % i] for i in range(1, 10)])

    def test_comments_cannot_change_block_boundaries(self):
        source = program("measure q -> c;") + "// classical { fake }\nclassical { // } ignored\nr1 = 7;\n}"
        _, assembly = adapter.compile_hybrid(source)
        emulator = TinyRISCVEmulator()
        emulator.load_program(assembly)
        self.assertEqual(emulator.execute()["x1"], 7)

    def test_signed_literals_and_spaced_classical_bits(self):
        result = self.execute("r1 = -5; r2 = c [ 0 ] + r1 - -2; r3 = +7;")
        self.assertEqual(result["x2"], -2)
        self.assertEqual(result["x3"], 7)

    def test_invalid_classical_input_is_not_silently_truncated(self):
        for body in ("r1 = 1; } r2 = 2; {", "r1 = c[2];", "r1 = c[17];"):
            with self.subTest(body=body), self.assertRaises(ValueError):
                adapter.compile_hybrid(program("") + "classical {" + body + "}")

    def test_measurement_bits_do_not_overlap_scratch_registers(self):
        source = program("", qubits=1, clbits=18) + "classical {r1 = 5 + c[17];}"
        with self.assertRaises(ValueError):
            adapter.compile_hybrid(source)

    def test_whole_register_measurements_are_expanded_once(self):
        source = ("OPENQASM 2.0; qreg a[1]; qreg b[1]; creg d[1]; creg e[1]; "
                  "x a[0]; measure a -> d; measure b -> e;")
        ops, _ = adapter.compile_hybrid(source)
        self.assertEqual(ops, ["x q[0];", "measure q[0] -> c[0];", "measure q[1] -> c[1];"])


if __name__ == "__main__":
    unittest.main()
