"""OpenQASM 2.0 parser for the LoomQ 12-gate whitelist.

Parses the restricted QASM 2.0 dialect used by the contest (qelib1 standard
gates only, no custom gate definitions) into a small intermediate
representation (IR) that every backend emitter and the reference simulator
share. One parser, one IR, many targets -- that is what makes the layer
"universal" instead of three hardcoded branches.
"""

from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# The contest gate whitelist (qelib1 standard gates).
WHITELIST_GATES = (
    "h", "x", "s", "sdg", "t", "tdg",
    "rz", "ry",
    "cx", "cu1", "swap",
    "ccx",
)

# Extra internal gates produced by validated decompositions (gate_identities.md).
INTERNAL_GATES = ("u1", "p")  # u1/p: diag(1, e^{i*theta})

GATE_ARITY = {
    "h": 1, "x": 1, "s": 1, "sdg": 1, "t": 1, "tdg": 1,
    "rz": 1, "ry": 1, "u1": 1, "p": 1,
    "cx": 2, "cu1": 2, "swap": 2,
    "ccx": 3,
}

GATE_NUM_PARAMS = {
    "h": 0, "x": 0, "s": 0, "sdg": 0, "t": 0, "tdg": 0,
    "rz": 1, "ry": 1, "u1": 1, "p": 1,
    "cx": 0, "cu1": 1, "swap": 0,
    "ccx": 0,
}


@dataclass
class Gate:
    """One gate application: name, numeric parameters, target qubit indices."""

    name: str
    params: Tuple[float, ...]
    qubits: Tuple[int, ...]


@dataclass
class Circuit:
    """Intermediate representation shared by all backends."""

    num_qubits: int
    num_clbits: int
    gates: List[Gate] = field(default_factory=list)
    # measurement map: list of (qubit_index, clbit_index)
    measurements: List[Tuple[int, int]] = field(default_factory=list)


def _eval_param(expr: str) -> float:
    """Safely evaluate a QASM parameter expression (numbers, pi, + - * / ())."""
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError("invalid parameter expression") from exc

    def _walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _walk(node.body)
        if isinstance(node, ast.Constant):
            if type(node.value) in (int, float):
                return float(node.value)
            raise ValueError("unsupported constant in parameter expression")
        if isinstance(node, ast.Name):
            if node.id == "pi":
                return math.pi
            raise ValueError("unknown name in parameter expression: %s" % node.id)
        if isinstance(node, ast.UnaryOp):
            value = _walk(node.operand)
            if isinstance(node.op, ast.USub):
                return -value
            if isinstance(node.op, ast.UAdd):
                return value
            raise ValueError("unsupported unary operator in parameter expression")
        if isinstance(node, ast.BinOp):
            left, right = _walk(node.left), _walk(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Pow):
                return left ** right
            raise ValueError("unsupported binary operator in parameter expression")
        raise ValueError("unsupported parameter expression")

    try:
        value = _walk(tree)
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("parameter must be a finite real number")
        return float(value)
    except (ArithmeticError, TypeError) as exc:
        raise ValueError("parameter must be a finite real number") from exc


def _split_statements(qasm: str) -> List[str]:
    """Strip comments and split a QASM program into statements."""
    lines = []
    for raw in qasm.splitlines():
        line = raw.split("//", 1)[0].strip()
        if line:
            lines.append(line)
    text = " ".join(lines)
    if text and not text.endswith(";"):
        raise ValueError("QASM statements must end with a semicolon")
    return [stmt.strip() for stmt in text.split(";") if stmt.strip()]


def parse_qasm2(qasm_str: str) -> Circuit:
    """Parse an OpenQASM 2.0 program (contest dialect) into a Circuit IR."""
    if not isinstance(qasm_str, str) or "OPENQASM" not in qasm_str:
        raise ValueError("not an OpenQASM program")

    statements = _split_statements(qasm_str)
    qregs: Dict[str, int] = {}
    cregs: Dict[str, int] = {}
    gates: List[Gate] = []
    measurements: List[Tuple[int, int]] = []
    # Flatten named registers into disjoint ranges in the shared IR.
    qubit_offset: Dict[str, int] = {}
    clbit_offset: Dict[str, int] = {}
    total_qubits = 0
    total_clbits = 0

    header_seen = False
    for position, stmt in enumerate(statements):
        if stmt.startswith("OPENQASM"):
            if position != 0 or not re.fullmatch(r"OPENQASM\s+2\.0", stmt):
                raise ValueError("program must start with exactly one OPENQASM 2.0 header")
            header_seen = True
            continue
        if not header_seen:
            raise ValueError("missing OPENQASM 2.0 header")
        if stmt.startswith("include"):
            if not re.fullmatch(r'include\s+"qelib1\.inc"', stmt):
                raise ValueError("only qelib1.inc is supported")
            continue
        m = re.fullmatch(r"qreg\s+([A-Za-z_]\w*)\[(\d+)\]", stmt)
        if m:
            name, size = m.group(1), int(m.group(2))
            if name in qregs or name in cregs or size <= 0:
                raise ValueError("register names must be unique and sizes positive")
            qubit_offset[name] = total_qubits
            qregs[name] = size
            total_qubits += size
            continue
        m = re.fullmatch(r"creg\s+([A-Za-z_]\w*)\[(\d+)\]", stmt)
        if m:
            name, size = m.group(1), int(m.group(2))
            if name in qregs or name in cregs or size <= 0:
                raise ValueError("register names must be unique and sizes positive")
            clbit_offset[name] = total_clbits
            cregs[name] = size
            total_clbits += size
            continue
        m = re.fullmatch(
            r"measure\s+([A-Za-z_]\w*)(?:\[(\d+)\])?\s*->\s*([A-Za-z_]\w*)(?:\[(\d+)\])?",
            stmt,
        )
        if m:
            qname, qidx, cname, cidx = m.group(1), m.group(2), m.group(3), m.group(4)
            if qname not in qregs or cname not in cregs:
                raise ValueError("measurement references undeclared register")
            if qidx is None and cidx is None:
                if qregs[qname] != cregs[cname]:
                    raise ValueError("register measurement size mismatch")
                for i in range(qregs[qname]):
                    measurements.append((qubit_offset[qname] + i, clbit_offset[cname] + i))
            elif qidx is not None and cidx is not None:
                if int(qidx) >= qregs[qname] or int(cidx) >= cregs[cname]:
                    raise ValueError("measurement index out of range")
                measurements.append(
                    (qubit_offset[qname] + int(qidx), clbit_offset[cname] + int(cidx))
                )
            else:
                raise ValueError("cannot mix register and indexed measurement")
            continue
        # gate application: name[(params)] q[i], q[j], ...
        m = re.fullmatch(
            r"([A-Za-z][A-Za-z0-9]*)(?:\((.+)\))?\s+([A-Za-z_]\w*(?:\[\d+\])?(?:\s*,\s*[A-Za-z_]\w*(?:\[\d+\])?)*)",
            stmt,
        )
        if m:
            if measurements:
                raise ValueError("only terminal measurements are supported; gates cannot follow measurement")
            name = m.group(1).lower()
            if name not in GATE_ARITY:
                raise ValueError("gate outside the contest whitelist: %s" % name)
            params: Tuple[float, ...] = ()
            if m.group(2) is not None:
                params = tuple(
                    _eval_param(part) for part in _split_top_level_commas(m.group(2))
                )
            operands: List[int] = []
            for token in m.group(3).split(","):
                token = token.strip()
                om = re.fullmatch(r"([A-Za-z_]\w*)\[(\d+)\]", token)
                if not om:
                    raise ValueError("whole-register gate operands are not supported: %s" % token)
                reg, idx = om.group(1), int(om.group(2))
                if reg not in qregs:
                    raise ValueError("gate references undeclared qreg: %s" % reg)
                if idx >= qregs[reg]:
                    raise ValueError("qubit index out of range: %s" % token)
                operands.append(qubit_offset[reg] + idx)
            if len(operands) != GATE_ARITY[name]:
                raise ValueError("gate %s expects %d operands" % (name, GATE_ARITY[name]))
            if len(set(operands)) != len(operands):
                raise ValueError("gate operands must be distinct qubits")
            if len(params) != GATE_NUM_PARAMS[name]:
                raise ValueError("gate %s expects %d parameters" % (name, GATE_NUM_PARAMS[name]))
            gates.append(Gate(name=name, params=params, qubits=tuple(operands)))
            continue
        raise ValueError("unparseable QASM statement: %r" % stmt)

    if not header_seen:
        raise ValueError("missing OPENQASM 2.0 header")
    if not qregs:
        raise ValueError("no qreg declared")

    return Circuit(
        num_qubits=total_qubits,
        num_clbits=total_clbits,
        gates=gates,
        measurements=measurements,
    )


def _split_top_level_commas(text: str) -> List[str]:
    parts, depth, current = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                raise ValueError("unbalanced parentheses in parameters")
        if ch == "," and depth == 0:
            if not "".join(current).strip():
                raise ValueError("empty parameter")
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if depth != 0:
        raise ValueError("unbalanced parentheses in parameters")
    if not "".join(current).strip():
        raise ValueError("empty parameter")
    parts.append("".join(current))
    return [part.strip() for part in parts]
