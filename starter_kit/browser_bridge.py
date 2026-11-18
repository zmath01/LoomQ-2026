"""Static Pages bridge: execute the same Python adapter in a browser worker."""
from . import adapter
from .loomq_core.editor import editor_response
from .loomq_cli import explain_counts


def handle(path: str, body: dict) -> dict:
    if path == '/api/editor':
        return editor_response(body)
    if path == '/api/run':
        qasm, target, shots = body['qasm'], body['target'], body['shots']
        if type(shots) is not int or not 1 <= shots <= 100_000:
            raise ValueError('shots must be an integer in 1..100000')
        result = adapter.run(qasm, target, shots)
        return {'ok': True, 'result': result,
                'transpilations': {t: adapter.transpile(qasm, t) for t in adapter.SUPPORTED_TARGETS},
                'explanation': explain_counts(result['counts'])}
    raise ValueError('This function requires the local Python service; Pages uses local reference simulation.')
