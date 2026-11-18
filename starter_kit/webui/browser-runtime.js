/* Loaded locally too, but enabled only by the static build's explicit flag. */
window.LoomQRuntime = (() => {
  let worker, nextId = 0;
  const pending = new Map();
  function call(path, body) {
    if (!worker) {
      worker = new Worker(new URL('./browser-worker.js', document.baseURI));
      worker.onmessage = ({data}) => {
        const entry = pending.get(data.id);
        if (!entry) return;
        pending.delete(data.id);
        data.error ? entry.reject(new Error(data.error)) : entry.resolve(data.result);
      };
      worker.onerror = () => {
        for (const entry of pending.values()) entry.reject(new Error('浏览器计算环境加载失败，请刷新后重试。'));
        pending.clear(); worker.terminate(); worker = null;
      };
    }
    return new Promise((resolve, reject) => {
      const id = ++nextId;
      pending.set(id, {resolve, reject}); worker.postMessage({id, path, body});
    });
  }
  async function request(path, options = {}) {
    const body = JSON.parse(options.body || '{}');
    if (path === '/api/health') return {ok:true, llm_configured:false, browser:true};
    if (path === '/api/backends') {
      const response = await fetch('./backend_capabilities.json');
      if (!response.ok) throw new Error('后端能力表加载失败');
      return {ok:true, backends:await response.json()};
    }
    if (path === '/api/circuit') {
      const parsed = await call('/api/editor', {qasm:body.qasm});
      const response = await fetch('./qiskit-diagrams.json');
      const cache = await response.json();
      const text = cache.diagrams[parsed.signature]?.[body.justify || 'left'] || null;
      return {ok:true, standard_text:text, qiskit:!!text, qiskit_version:cache.version,
        num_qubits:parsed.model.qubits, num_clbits:parsed.model.clbits};
    }
    return call(path, body);
  }
  return {request};
})();
