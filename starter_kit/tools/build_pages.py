#!/usr/bin/env python3
"""Build a static editor using the existing Python core in a Pyodide worker.

Qiskit itself produces the cached example diagrams; arbitrary live Qiskit
drawings and the LLM remain features of the local Python service.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / 'starter_kit'
sys.path.insert(0, str(ROOT))
from starter_kit.loomq_core.editor import editor_model, signature  # noqa: E402

PYODIDE_VERSION = '0.27.7'
PYODIDE_URL = f'https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/'
RUNTIME_FILES = ('pyodide.js', 'pyodide.asm.js', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json')


def build(output: Path, cache: Path) -> dict:
    import qiskit
    from qiskit import QuantumCircuit

    # Output must be a dedicated generated folder, never a source directory.
    output = output.resolve()
    if output == ROOT or output == KIT or ROOT not in output.parents or output.name != 'site':
        raise ValueError('output must be a site/ directory within the repository')
    output.mkdir(parents=True, exist_ok=True)
    for source in (KIT / 'webui').iterdir():
        if source.suffix in ('.html', '.js'):
            shutil.copy2(source, output / source.name)
    index = output / 'index.html'
    index.write_text(index.read_text().replace('<head>', '<head>\n<script>window.LOOMQ_STATIC=true;</script>', 1))
    shutil.copytree(KIT / 'circuits', output / 'circuits', dirs_exist_ok=True)
    shutil.copy2(KIT / 'backend_capabilities.json', output / 'backend_capabilities.json')
    diagrams = {}
    for source in sorted((KIT / 'circuits').glob('*.qasm')):
        qasm = source.read_text()
        model = editor_model(qasm)
        circuit = QuantumCircuit.from_qasm_str(qasm)
        diagrams[signature(model)] = {mode: str(circuit.draw(output='text', justify=mode, fold=-1, cregbundle=False))
                                      for mode in ('left', 'none')}
    (output / 'qiskit-diagrams.json').write_text(json.dumps({'version': qiskit.__version__, 'diagrams': diagrams}))
    python_files = [KIT / name for name in ('__init__.py', 'adapter.py', 'llm_client.py', 'loomq_cli.py', 'browser_bridge.py')]
    python_files += sorted((KIT / 'loomq_core').glob('*.py'))
    with zipfile.ZipFile(output / 'loomq-python.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for source in python_files:
            archive.write(source, 'starter_kit/' + source.relative_to(KIT).as_posix())
        archive.write(KIT / 'backend_capabilities.json', 'starter_kit/backend_capabilities.json')
    runtime = output / 'vendor' / 'pyodide'
    runtime.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    for name in RUNTIME_FILES + ('LICENSE',):
        cached = cache / (PYODIDE_VERSION + '-' + name)
        if not cached.exists():
            url = PYODIDE_URL + name if name != 'LICENSE' else f'https://raw.githubusercontent.com/pyodide/pyodide/{PYODIDE_VERSION}/LICENSE'
            temporary = cached.with_suffix(cached.suffix + '.part')
            try:
                with urllib.request.urlopen(url, timeout=90) as response:
                    data = response.read()
                if not data:
                    raise RuntimeError('empty runtime download: ' + name)
                temporary.write_bytes(data)
                temporary.replace(cached)
            finally:
                temporary.unlink(missing_ok=True)
        shutil.copy2(cached, runtime / name)
    (output / '.nojekyll').touch()
    result = {'qiskit': qiskit.__version__, 'pyodide': PYODIDE_VERSION, 'example_diagrams': len(diagrams),
              'simulation': 'existing Python adapter in a browser worker', 'cloud_execution': False}
    (output / 'build-info.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'site')
    parser.add_argument('--runtime-cache', type=Path, default=ROOT / '.pages-runtime-cache')
    args = parser.parse_args()
    print(json.dumps(build(args.output, args.runtime_cache)))
