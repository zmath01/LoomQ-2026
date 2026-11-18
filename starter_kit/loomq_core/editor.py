"""Editor transport using the existing QASM parser; no second circuit parser."""

from __future__ import annotations

import hashlib
import json

from .qasm import GATE_ARITY, GATE_NUM_PARAMS, _eval_param, parse_qasm2


def editor_model(qasm: str) -> dict:
    circuit = parse_qasm2(qasm)
    if circuit.num_qubits > 12 or circuit.num_clbits > 64 or len(circuit.gates) + len(circuit.measurements) > 500:
        raise ValueError("graphical editor supports up to 12 qubits, 64 classical bits and 500 operations (gates and measurements)")
    return {
        "qubits": circuit.num_qubits,
        "clbits": circuit.num_clbits,
        "gates": [{"name": gate.name, "qubits": list(gate.qubits), "params": list(gate.params)}
                  for gate in circuit.gates],
        "measurements": [list(pair) for pair in circuit.measurements],
    }


def model_qasm(model: dict) -> str:
    if not isinstance(model, dict):
        raise ValueError("editor circuit must be an object")
    n, m = model.get("qubits"), model.get("clbits")
    if type(n) is not int or not 1 <= n <= 12 or type(m) is not int or not 0 <= m <= 64:
        raise ValueError("invalid editor register sizes")
    gates, measurements = model.get("gates"), model.get("measurements")
    if not isinstance(gates, list) or not isinstance(measurements, list) or len(gates) + len(measurements) > 500:
        raise ValueError("invalid editor operations")
    lines = ['OPENQASM 2.0;', 'include "qelib1.inc";', f'qreg q[{n}];']
    if m:
        lines.append(f'creg c[{m}];')
    for gate in gates:
        if not isinstance(gate, dict):
            raise ValueError("invalid editor gate")
        name, qubits, params = gate.get("name"), gate.get("qubits"), gate.get("params")
        if not isinstance(name, str) or name not in GATE_ARITY or not isinstance(qubits, list) or not isinstance(params, list):
            raise ValueError("invalid editor gate")
        if len(qubits) != GATE_ARITY[name] or len(params) != GATE_NUM_PARAMS[name]:
            raise ValueError("wrong editor gate arity")
        if any(type(q) is not int or not 0 <= q < n for q in qubits):
            raise ValueError("editor qubit index out of range")
        angles = [_eval_param(str(value)) for value in params]
        suffix = '(' + ', '.join(repr(angle) for angle in angles) + ')' if angles else ''
        lines.append(name + suffix + ' ' + ', '.join(f'q[{q}]' for q in qubits) + ';')
    for pair in measurements:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2 or any(type(x) is not int for x in pair):
            raise ValueError("invalid measurement mapping")
        q, c = pair
        lines.append(f'measure q[{q}] -> c[{c}];')
    result = '\n'.join(lines) + '\n'
    editor_model(result)  # All semantic validation stays in the canonical parser.
    return result


def signature(model: dict) -> str:
    return hashlib.sha256(json.dumps(model, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def editor_response(body: dict) -> dict:
    qasm = model_qasm(body['model']) if 'model' in body else body.get('qasm', '')
    model = editor_model(qasm)
    return {"ok": True, "model": model, "qasm": qasm, "signature": signature(model)}
