const {test}=require('node:test');
const assert=require('node:assert/strict');
const {layout,insert}=require('../starter_kit/webui/editor-layout.js');
const gate=(name,qubits,params=[])=>({name,qubits,params});
const model=gates=>({qubits:4,clbits:2,gates,measurements:[[3,0],[0,1]]});

test('independent gates may share a column; same-wire source order is preserved',()=>{
  const placed=layout(model([gate('h',[0]),gate('x',[2]),gate('rz',[0],[-Math.PI/2])]));
  assert.deepEqual(placed.map(p=>p.column),[0,0,1]);
});
test('new spans cannot pass through existing gates, and vice versa',()=>{
  for(const gates of [
    [gate('h',[1]),gate('cx',[0,2])],
    [gate('cx',[0,2]),gate('h',[1])],
    [gate('cx',[0,2]),gate('cx',[1,3])],
  ])assert.notEqual(...layout(model(gates)).map(p=>p.column));
});
test('disjoint visual spans share a column, including reversed operand order',()=>{
  assert.deepEqual(layout(model([gate('cx',[1,0]),gate('swap',[3,2])])).map(p=>p.column),[0,0]);
});
test('serial drawing places each gate in a separate column without mutating input',()=>{
  const source=model([gate('h',[0]),gate('ry',[2],[-0.12345678901234567])]);
  const before=JSON.stringify(source);
  assert.deepEqual(layout(source,'none').map(p=>p.column),[0,1]);
  layout(source,'left');assert.equal(JSON.stringify(source),before);
});
test('insertion respects earlier visible operations on both operands and retains measurements',()=>{
  const source=model([gate('h',[0]),gate('x',[0]),gate('h',[1])]);
  const result=insert(source,gate('cx',[1,0]),1);
  assert.deepEqual(result.gates.map(g=>g.name),['h','h','cx','x']);
  assert.deepEqual(result.measurements,source.measurements);
  assert.equal(source.gates.length,3);
});
