/* Pyodide runs off the UI thread; the zip contains the existing Python core. */
importScripts('./vendor/pyodide/pyodide.js');
let runtime;
async function ready() {
  if (!runtime) runtime = (async () => {
    const py = await loadPyodide({indexURL: new URL('./vendor/pyodide/', self.location.href).href});
    const response = await fetch('./loomq-python.zip');
    if (!response.ok) throw new Error('Cannot load the LoomQ Python core');
    py.unpackArchive(await response.arrayBuffer(), 'zip', {extractDir: '/app'});
    await py.runPythonAsync('import sys, json\nsys.path[:0] = ["/app", "/app/starter_kit"]\nfrom starter_kit.browser_bridge import handle');
    return py;
  })().catch(error => { runtime = null; throw error; });
  return runtime;
}
let queue = Promise.resolve();
self.onmessage = ({data}) => {
  queue = queue.then(async () => {
    try {
      const py = await ready();
      py.globals.set('request_json', JSON.stringify(data));
      const text = await py.runPythonAsync('request = json.loads(request_json)\njson.dumps(handle(request["path"], request["body"]))');
      self.postMessage({id: data.id, result: JSON.parse(text)});
    } catch (error) {
      self.postMessage({id: data.id, error: String(error.message || error)});
    }
  });
};
