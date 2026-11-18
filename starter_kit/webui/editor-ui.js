/* Interactive view of the canonical Python circuit model. No QASM parser here. */
let circMode='grid',pendingGate=null,pendingMulti=null;
let circ={qubits:2,clbits:2,gates:[],measurements:[[0,0],[1,1]]};
let editorValid=false,editorBusy=false,editorEpoch=0,acceptedQasm='';
function drawingJustify(){return document.getElementById('draw-justify')?.value||'left';}
function fmtParam(value){
  if(value===0)return '0';
  for(const n of [1,2,3,4,6,8,12,16,32]){
    const m=Math.round(value/Math.PI*n);
    if(m!==0&&Math.abs(value-m*Math.PI/n)<=1e-12*Math.max(1,Math.abs(value)))
      return (m===1?'':m===-1?'-':m+'*')+'pi'+(n===1?'':'/'+n);
  }
  return String(value);
}
function editorNotice(message,error=false){
  const el=document.getElementById('editor-status');
  el.textContent=message;el.classList.toggle('error',error);
}
function readyEditor(){
  if(!editorValid||acceptedQasm!==$('qasm-editor').value){editorNotice('请先修正 QASM 并等待解析完成；原始代码不会被覆盖。',true);return false;}
  if(editorBusy){editorNotice('正在保存本次编辑，请稍候。');return false;}
  return true;
}
async function syncFromQasm(){
  const source=$('qasm-editor').value,epoch=++editorEpoch;
  editorValid=false;pendingGate=null;pendingMulti=null;
  editorNotice('正在校验电路…');
  try{
    const data=await api('/api/editor',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({qasm:source})});
    if(epoch!==editorEpoch||source!==$('qasm-editor').value)return;
    circ=data.model;acceptedQasm=source;editorValid=true;
    editorNotice('已校验：'+circ.gates.length+' 个门，'+circ.qubits+' 量子比特，'+circ.clbits+' 经典比特。列压缩仅改变排版，不优化底层电路。');
    if(circMode==='grid')renderGrid();else await drawCircuitFromEditor();
  }catch(error){
    if(epoch!==editorEpoch)return;
    editorNotice('解析失败：'+error.message,true);
    $('circuit-svg').textContent='QASM 无效，图形编辑已暂停；请修正下方原文。';
  }
}
async function commitEditor(model){
  if(!readyEditor())return false;
  const source=$('qasm-editor').value,epoch=++editorEpoch;
  editorBusy=true;
  try{
    const data=await api('/api/editor',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model})});
    if(epoch!==editorEpoch||source!==$('qasm-editor').value)return false;
    circ=data.model;$('qasm-editor').value=data.qasm;acceptedQasm=data.qasm;editorValid=true;curPreset=null;
    $('lab-result').style.display='none';$('lab-ir').style.display='none';$('hist-area').textContent='（电路已修改，请重新运行）';
    editorNotice('编辑已校验。保留现有角度及测量映射；只有明确的编辑操作才会修改电路。');
    renderGrid();return true;
  }catch(error){editorNotice('编辑未保存：'+error.message,true);return false;}
  finally{editorBusy=false;}
}
function renderGrid(){
  if(!editorValid)return;
  const placed=LoomQLayout.layout(circ,drawingJustify());
  const gateCols=Math.max(0,...placed.map(p=>p.column+1));
  const cols=Math.max(1,gateCols+circ.measurements.length+1),cells=new Map();
  for(const p of placed)for(const q of circ.gates[p.index].qubits)cells.set(q+':'+p.column,p);
  const rows=[],pm=pendingMulti;
  if(pm){editorNotice(pm.name==='swap'?'SWAP：点击另一根线选择交换比特（不是控制位）。':'目标固定在 q['+pm.tw+']；点击其他量子线选择 '+(pm.q-1)+' 个控制位。');}
  for(let q=0;q<circ.qubits;q++){
    rows.push('<div class="qwire">q['+q+']</div>');
    for(let c=0;c<cols;c++){
      const p=cells.get(q+':'+c);let inner='',attrs='';
      if(p){
        const gate=circ.gates[p.index],target=gate.qubits[gate.qubits.length-1];
        const angle=gate.params.length?'('+fmtParam(gate.params[0])+')':'';
        if(gate.qubits.length===1)inner='<span class="gchip">'+escapeHtml(gate.name.toUpperCase()+angle)+'</span>';
        else if(gate.name==='swap')inner='<span class="swap-mark">×</span>';
        else if(q!==target)inner='<span class="gctl" aria-hidden="true"></span>';
        else if(gate.name==='cu1')inner='<span class="gchip">P'+escapeHtml(angle)+'</span>';
        else inner='<span class="gtgt">⊕</span>';
        if(q===p.lo&&p.hi>p.lo)inner+='<span class="vlink" style="top:50%;height:'+((p.hi-p.lo)*46)+'px"></span>';
        attrs=' data-gate="'+p.index+'" title="'+escapeHtml(gate.name.toUpperCase()+angle+' · '+gate.qubits.map(w=>'q['+w+']').join(', ')+'；点击删除该门')+'"';
      }
      const mi=c-gateCols,measurement=circ.measurements[mi];
      if(measurement&&measurement[0]===q){
        inner='<span class="gchip measure-mark">M</span><span class="measurement-link" style="top:50%;height:'+((circ.qubits-q)*46)+'px"></span>';
        attrs=' data-measure="'+mi+'" title="测量 q['+q+'] → c['+measurement[1]+']；点击删除该测量"';
      }
      if(pm&&c===Math.min(pm.c,cols-1)){
        if(q===pm.tw)inner+='<span class="pick-ctl sel">'+(pm.name==='swap'?'×':'T')+'</span>';
        else inner+='<span class="pick-ctl'+(pm.sel.includes(q)?' sel':'')+'">'+(pm.name==='swap'?'×':'●')+'</span>';
      }
      rows.push('<button type="button" class="cell" data-w="'+q+'" data-c="'+c+'" aria-label="q['+q+'], 第 '+(c+1)+' 列"'+attrs+'>'+inner+'</button>');
    }
  }
  if(circ.clbits){
    rows.push('<div class="qwire">c['+circ.clbits+']</div>');
    for(let c=0;c<cols;c++){
      const pair=circ.measurements[c-gateCols];
      rows.push('<div class="cell classical-cell">'+(pair?'<span class="classical-index">↓ '+pair[1]+'</span>':'')+'</div>');
    }
  }
  const hint=pm?'<button type="button" class="btn ghost small" onclick="cancelPick()">取消选线</button>':'';
  $('circuit-svg').innerHTML=hint+'<div class="circ-grid" style="grid-template-columns:52px repeat('+cols+',minmax(74px,max-content))">'+rows.join('')+'</div>'+
    '<p class="muted circuit-note">'+(circ.measurements.length?'M 表示测量；双线 c['+circ.clbits+'] 是经典寄存器总线，箭头下标是写入位。':'无显式测量；运行接口默认读取所有量子比特。')+'</p>';
  $('circuit-svg').querySelectorAll('button.cell').forEach(cell=>{
    cell.addEventListener('click',async()=>{
      const q=Number(cell.dataset.w),c=Number(cell.dataset.c);
      if(pendingMulti){if(q!==pendingMulti.tw)await pickControl(q);return;}
      if(pendingGate){const gate=pendingGate;pendingGate=null;await placeFromPalette(gate.n,gate.q,gate.p,q,c);return;}
      if(cell.dataset.gate!==undefined){const i=Number(cell.dataset.gate);await commitEditor({...circ,gates:circ.gates.filter((_,index)=>index!==i)});}
      else if(cell.dataset.measure!==undefined){const i=Number(cell.dataset.measure);await commitEditor({...circ,measurements:circ.measurements.filter((_,index)=>index!==i)});}
    });
    cell.addEventListener('dragover',event=>{event.preventDefault();cell.classList.add('drag-over');});
    cell.addEventListener('dragleave',()=>cell.classList.remove('drag-over'));
    cell.addEventListener('drop',async event=>{
      event.preventDefault();cell.classList.remove('drag-over');
      const name=event.dataTransfer.getData('text/plain'),gate=GATES12.find(g=>g.n===name);
      if(gate)await placeFromPalette(gate.n,gate.q||1,!!gate.p,Number(cell.dataset.w),Number(cell.dataset.c));
    });
  });
}
async function placeFromPalette(name,q,parameterized,w,c){
  if(!readyEditor())return;
  if(circ.qubits<q){editorNotice('至少需要 '+q+' 个量子比特。',true);return;}
  let params=[];
  if(parameterized){const text=prompt('角度（弧度），例如 -pi/2、3*pi/4；留空默认 pi/4');if(text===null)return;params=[text.trim()||'pi/4'];}
  if(q>1){pendingMulti={name,q,params,tw:w,c,sel:[]};renderGrid();return;}
  await commitEditor(LoomQLayout.insert(circ,{name,qubits:[w],params},c,drawingJustify()));
}
async function pickControl(q){
  const pick=pendingMulti;if(!pick||q===pick.tw)return;
  pick.sel=pick.sel.includes(q)?pick.sel.filter(w=>w!==q):[...pick.sel,q];
  if(pick.sel.length===pick.q-1){
    pendingMulti=null;
    await commitEditor(LoomQLayout.insert(circ,{name:pick.name,qubits:[...pick.sel,pick.tw],params:pick.params},pick.c,drawingJustify()));
  }else renderGrid();
}
function cancelPick(){pendingMulti=null;pendingGate=null;renderGrid();}
function pendingPick(n,q,p){if(!readyEditor())return;pendingMulti=null;pendingGate={n,q,p};editorNotice('已选择 '+n.toUpperCase()+'；点击电路中的量子线放置。');}
function dragStart(event){event.dataTransfer.setData('text/plain',event.currentTarget.dataset.g);}
function initPalette(){
  $('gate-palette').innerHTML=GATES12.map(g=>'<button type="button" class="gatebtn'+(g.p?' cfg':'')+'" draggable="true" data-g="'+g.n+'" ondragstart="dragStart(event)" onclick="pendingPick(\''+g.n+'\','+(g.q||1)+','+(g.p?1:0)+')" title="'+escapeHtml(gateTip(g.n,!!g.p))+'">'+g.label+'</button>').join('');
}
async function clearGrid(){
  if(!editorValid){$('qasm-editor').value='OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[2];\ncreg c[2];\nmeasure q -> c;\n';await syncFromQasm();return;}
  await commitEditor({qubits:2,clbits:2,gates:[],measurements:[[0,0],[1,1]]});
}
async function addWire(){
  if(!readyEditor())return;if(circ.qubits>=12){editorNotice('图形编辑最多 12 比特。',true);return;}
  const identity=circ.clbits===circ.qubits&&circ.measurements.length===circ.qubits&&circ.measurements.every((p,i)=>p[0]===i&&p[1]===i);
  const model={...circ,qubits:circ.qubits+1};
  if(identity){model.clbits++;model.measurements=[...circ.measurements,[circ.qubits,circ.qubits]];}
  await commitEditor(model);
}
async function removeWire(){
  if(!readyEditor())return;const last=circ.qubits-1;
  if(last<1){editorNotice('至少保留 1 个量子比特。',true);return;}
  if(circ.gates.some(g=>g.qubits.includes(last))){editorNotice('最后一根线仍参与量子门（包括控制位），请先删除该门。',true);return;}
  await commitEditor({...circ,qubits:last,measurements:circ.measurements.filter(pair=>pair[0]!==last)});
}
async function measureAll(){if(readyEditor())await commitEditor({...circ,clbits:circ.qubits,measurements:Array.from({length:circ.qubits},(_,i)=>[i,i])});}
async function circView(mode){
  circMode=mode;$('btn-grid').classList.toggle('on',mode==='grid');$('btn-qiskit').classList.toggle('on',mode==='qiskit');
  await syncFromQasm();
}
function changeJustify(){cancelPick();if(circMode==='grid')renderGrid();else drawCircuitFromEditor();}
function loadExample(key){$('preset').value=key;return loadPreset(key);}
