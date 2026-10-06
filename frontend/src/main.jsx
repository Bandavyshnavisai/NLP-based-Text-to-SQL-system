import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const headers = {'ngrok-skip-browser-warning':'true'};

async function api(path, options={}) {
  const h = {...headers, ...(options.headers||{})};
  const r = await fetch(`${API}${path}`, {...options, headers:h});
  const text = await r.text();
  let data; try { data = JSON.parse(text); } catch { throw new Error(`Backend returned non-JSON (${r.status}). Check API URL/ngrok.`); }
  if (!r.ok) throw new Error(data.detail || data.error || `HTTP ${r.status}`);
  return data;
}

function App(){
  const [health,setHealth]=useState(null), [dbs,setDbs]=useState([]), [db,setDb]=useState(''), [question,setQuestion]=useState(''), [schema,setSchema]=useState(null), [result,setResult]=useState(null), [busy,setBusy]=useState(false), [uploading,setUploading]=useState(false), [msg,setMsg]=useState('');
  const load=async()=>{try{const [h,d]=await Promise.all([api('/health'),api('/databases')]);setHealth(h);setDbs(d.databases);if(!db&&d.databases[0])setDb(d.databases[0].id)}catch(e){setHealth({status:'error',error:e.message})}};
  useEffect(()=>{load()},[]);
  useEffect(()=>{if(db)api(`/schema?database=${encodeURIComponent(db)}`).then(setSchema).catch(()=>setSchema(null))},[db]);
  const upload=async e=>{const file=e.target.files?.[0]; if(!file)return; setUploading(true);setMsg('');try{const fd=new FormData();fd.append('file',file);const d=await api('/upload-database',{method:'POST',body:fd,headers:{}});setMsg(`Uploaded ${d.filename}`);await load();setDb(d.id)}catch(err){setMsg(err.message)}finally{setUploading(false);e.target.value=''}};
  const run=async()=>{if(!db||!question.trim())return;setBusy(true);setResult(null);try{setResult(await api('/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({database:db,question})}))}catch(e){setResult({success:false,error:e.message})}finally{setBusy(false)}};
  return <div className="app"><header><div><h1>Natural Language → SQL</h1><p>Ask questions about any uploaded SQLite database.</p></div><span className={health?.model_loaded?'pill ok':'pill'}>{health?.model_loaded?'Model ready':'Model not connected'}</span></header>
    <main><section className="card"><h2>1. Database</h2><div className="row"><select value={db} onChange={e=>setDb(e.target.value)}><option value="">Select database</option>{dbs.map(x=><option key={x.id} value={x.id}>{x.name}{x.uploaded?' (uploaded)':''}</option>)}</select><label className="upload">{uploading?'Uploading…':'Upload .db / .sqlite'}<input type="file" accept=".db,.sqlite,.sqlite3" onChange={upload} disabled={uploading}/></label></div>{msg&&<div className="msg">{msg}</div>}</section>
    <section className="card"><h2>2. Ask a question</h2><textarea value={question} onChange={e=>setQuestion(e.target.value)} placeholder="Example: Show all students who scored more than 80."/><div className="examples"><button onClick={()=>setQuestion('Show all rows from the first table.')}>Simple query</button><button onClick={()=>setQuestion('Show the top 10 records ordered by the first numeric column descending.')}>Top 10</button></div><button className="primary" onClick={run} disabled={busy||!db||!question.trim()}>{busy?'Generating and running…':'Generate & Run'}</button></section>
    {schema&&<section className="card"><h2>Schema</h2><div className="schema">{schema.tables.map(t=><div key={t.name}><b>{t.name}</b><span>{t.columns.map(c=>`${c.name} ${c.type||'TEXT'}`).join(' · ')}</span></div>)}</div></section>}
    {result&&<section className="card"><h2>Result</h2>{result.sql&&<><div className="label">Generated SQL</div><pre>{result.sql}</pre></>}{result.error&&<div className="error">{result.error}</div>}{result.execution?.success&&<><div className="stats">{result.execution.row_count} rows · {result.execution.time_ms} ms</div><div className="tableWrap"><table><thead><tr>{result.execution.columns.map(c=><th key={c}>{c}</th>)}</tr></thead><tbody>{result.execution.rows.map((r,i)=><tr key={i}>{result.execution.columns.map(c=><td key={c}>{String(r[c] ?? '')}</td>)}</tr>)}</tbody></table></div></>}{result.validation&&<div className="validation">Validation: {result.validation.valid?'PASS':'FAIL'} · read-only: {String(result.validation.read_only)}</div>}</section>}
    </main><footer>API: {API}</footer></div>
}
createRoot(document.getElementById('root')).render(<App/>);
