/* Display scheduling only: never changes gates, angles, connectivity or routing. */
(function (root) {
  'use strict';
  function layout(model, justify = 'left') {
    const last = Array(model.qubits).fill(-1), occupied = [], placed = [];
    model.gates.forEach((gate, index) => {
      const lo = Math.min(...gate.qubits), hi = Math.max(...gate.qubits);
      let column = justify === 'none' ? index : Math.max(...gate.qubits.map(q => last[q])) + 1;
      while (occupied[column] && Array.from({length: hi - lo + 1}, (_, i) => lo + i).some(q => occupied[column].has(q))) column++;
      if (!occupied[column]) occupied[column] = new Set();
      for (let q = lo; q <= hi; q++) occupied[column].add(q);
      for (const q of gate.qubits) last[q] = column;
      placed.push({ index, column, lo, hi });
    });
    return placed;
  }
  function insert(model, gate, column, justify = 'left') {
    const placed = layout(model, justify).sort((a, b) => a.column - b.column || a.index - b.index);
    // A linear extension of the wire dependencies. Reordering existing gates
    // here only swaps operations on disjoint qubit sets, hence preserves U.
    return {...model, gates: [
      ...placed.filter(p => p.column < column).map(p => model.gates[p.index]), gate,
      ...placed.filter(p => p.column >= column).map(p => model.gates[p.index]),
    ]};
  }
  const api = { layout, insert };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.LoomQLayout = api;
})(typeof globalThis === 'undefined' ? this : globalThis);
