import importlib.util
import json
import math
import random
import shutil
import subprocess
import unittest
from pathlib import Path

from starter_kit.loomq_core.editor import editor_model, model_qasm, editor_response
from starter_kit.loomq_core.qasm import Circuit, Gate, parse_qasm2
from starter_kit.loomq_core.simulator import statevector, simulate_counts
from starter_kit.loomq_cli import explain_counts

ROOT = Path(__file__).resolve().parents[1]


class EditorContractTests(unittest.TestCase):
    def test_single_line_expressions_and_named_registers_use_the_existing_parser(self):
        source = ('OPENQASM 2.0; include "qelib1.inc"; qreg a[1]; qreg b[2]; creg out[1]; '
                  'ry(-pi/2) a[0]; cu1(3*pi/4) a[0],b[1]; rz(0.12345678901234567) b[0]; measure b[1] -> out[0];')
        model = editor_model(source)
        self.assertEqual(model['qubits'], 3)
        self.assertEqual(model['clbits'], 1)
        self.assertEqual(model['measurements'], [[2, 0]])
        self.assertEqual(model['gates'][0]['params'], [-math.pi / 2])
        self.assertEqual(model['gates'][1]['params'], [3 * math.pi / 4])
        actual = statevector(parse_qasm2(model_qasm(model)))
        expected = statevector(parse_qasm2(source))
        self.assertLess(max(abs(a-b) for a,b in zip(actual, expected)), 1e-14)

    def test_measurement_width_mapping_and_write_order_survive_round_trip(self):
        source = 'OPENQASM 2.0; qreg q[3]; creg c[1]; x q[2]; measure q[2] -> c[0]; measure q[0] -> c[0];'
        model = editor_model(source)
        result = parse_qasm2(model_qasm(model))
        self.assertEqual(result.num_clbits, 1)
        self.assertEqual(result.measurements, [(2, 0), (0, 0)])
        self.assertEqual(simulate_counts(result, 16), {'0': 16})

    def test_no_explicit_measurement_is_not_silently_replaced(self):
        model = editor_model('OPENQASM 2.0; qreg q[1]; h q[0];')
        self.assertEqual(model['clbits'], 0)
        self.assertNotIn('measure', model_qasm(model))
        self.assertNotIn('creg', model_qasm(model))

    def test_invalid_input_is_rejected_instead_of_returning_a_partial_circuit(self):
        for source in ('OPENQASM 2.0; qreg q[2]; h q[0]; invalid q[1];',
                       'OPENQASM 2.0; qreg q[13]; h q[0];'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                editor_response({'qasm': source})

    def test_editor_limits_cover_measurements_and_malformed_gate_names(self):
        model = editor_model('OPENQASM 2.0; qreg q[1]; creg c[1];')
        model['measurements'] = [[0, 0]] * 501
        with self.assertRaises(ValueError):
            model_qasm(model)
        with self.assertRaises(ValueError):
            editor_model('OPENQASM 2.0; qreg q[1]; creg c[1];' + 'measure q[0] -> c[0];' * 501)
        model['measurements'] = []
        model['gates'] = [{'name': [], 'qubits': [0], 'params': []}]
        with self.assertRaises(ValueError):
            model_qasm(model)

    def test_model_parameters_are_validated_without_eval_or_rounding(self):
        model = editor_model('OPENQASM 2.0; qreg q[1]; rz(0.12345678901234567) q[0];')
        self.assertEqual(editor_model(model_qasm(model)), model)
        model['gates'][0]['params'] = ['-3*pi/4']
        self.assertEqual(editor_model(model_qasm(model))['gates'][0]['params'], [-3*math.pi/4])
        for bad in ('nan', '1/0', '__import__("os")', 'pi); x q[0]; rz(0'):
            model['gates'][0]['params'] = [bad]
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                model_qasm(model)

    def test_histograms_do_not_claim_entanglement_or_exact_probabilities(self):
        self.assertIn('不能证明纠缠', explain_counts({'00': 500, '11': 500}))
        self.assertNotIn('各约占一半', explain_counts({'0': 999, '1': 1}))
        self.assertNotIn('完全确定', explain_counts({'0': 10}))

    @unittest.skipUnless(shutil.which('node'), 'Node.js is needed for the shared browser layout')
    def test_display_reordering_preserves_complex_amplitudes(self):
        rng = random.Random(20261118)
        models = []
        for _ in range(30):
            gates = []
            for _ in range(30):
                name = rng.choice(('h', 'x', 's', 'sdg', 't', 'tdg', 'rz', 'ry', 'cx', 'cu1', 'swap', 'ccx'))
                arity = 3 if name == 'ccx' else 2 if name in ('cx', 'cu1', 'swap') else 1
                gates.append({'name': name, 'qubits': rng.sample(range(4), arity),
                              'params': [rng.uniform(-math.pi, math.pi)] if name in ('rz', 'ry', 'cu1') else []})
            models.append({'qubits': 4, 'clbits': 0, 'gates': gates, 'measurements': []})
        script = "const fs=require('fs'),{layout}=require('./starter_kit/webui/editor-layout.js');console.log(JSON.stringify(JSON.parse(fs.readFileSync(0,'utf8')).map(m=>layout(m).sort((a,b)=>a.column-b.column||a.index-b.index).map(p=>p.index))));"
        orders = json.loads(subprocess.check_output(['node', '-e', script], input=json.dumps(models), text=True, cwd=ROOT))
        for model, order in zip(models, orders):
            original = [Gate(g['name'], tuple(g['params']), tuple(g['qubits'])) for g in model['gates']]
            reordered = [original[i] for i in order]
            for basis in (0, 3, 9, 15):
                prep = [Gate('x', (), (q,)) for q in range(4) if basis & (1 << q)]
                before = statevector(Circuit(4, 0, prep + original))
                after = statevector(Circuit(4, 0, prep + reordered))
                self.assertLess(max(abs(a-b) for a,b in zip(before, after)), 1e-12)

    @unittest.skipUnless(importlib.util.find_spec('qiskit'), 'optional Qiskit SDK is not installed')
    def test_core_and_editor_round_trip_agree_with_qiskit(self):
        from qiskit import QuantumCircuit
        from qiskit.quantum_info import Statevector

        source = ('OPENQASM 2.0; include "qelib1.inc"; qreg q[3]; creg c[2]; '
                  'h q[0]; ry(-pi/2) q[1]; rz(3*pi/4) q[0]; cx q[1],q[2]; '
                  'cu1(-pi/3) q[2],q[0]; swap q[0],q[2]; ccx q[2],q[0],q[1]; '
                  'measure q[2] -> c[0]; measure q[0] -> c[1];')
        canonical = model_qasm(editor_model(source))
        qc = QuantumCircuit.from_qasm_str(source).remove_final_measurements(inplace=False)
        expected = list(Statevector.from_instruction(qc))
        actual = statevector(parse_qasm2(canonical))
        self.assertLess(max(abs(a-b) for a,b in zip(expected, actual)), 1e-12)


if __name__ == '__main__':
    unittest.main()
