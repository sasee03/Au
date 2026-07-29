import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Sidebar from '../components/Sidebar'
import TopNav from '../components/TopNav'

const API = 'http://localhost:4000/api'
const TABS = ['Connect','Select','Configure Pipeline','Bronze Layer','Silver Layer','Gold Layer','Report']
const TAB_ROUTES = { Connect:'connect', Select:'select', 'Configure Pipeline':'pipeline-config', 'Bronze Layer':'bronze', 'Silver Layer':'silver', 'Gold Layer':'gold', Report:'report' }

export default function GoldLayerPage() {
  const { projectId } = useParams()
  const navigate = useNavigate()

  const [requirement, setRequirement] = useState('')
  const [kpis,        setKpis]        = useState([])
  const [sqlMap,      setSqlMap]      = useState({})
  const [editingSQL,  setEditingSQL]  = useState({})
  const [selectedKpi, setSelectedKpi] = useState('')
  const [generating,  setGenerating]  = useState(false)
  const [executing,   setExecuting]   = useState(false)
  const [executed,    setExecuted]    = useState(false)
  const [goldResult,  setGoldResult]  = useState(null)  // full execute response
  const [preview,     setPreview]     = useState([])
  const [previewCols, setPreviewCols] = useState([])
  const [schemaInfo,  setSchemaInfo]  = useState('')

  useEffect(() => {
    setSchemaInfo(sessionStorage.getItem('aurum_schema_info') || '')
  }, [])

  // ── Generate KPI Plan ───────────────────────────────────────────────────
  const handleGenerateKPI = async () => {
    if (!requirement.trim()) return
    setGenerating(true)
    setKpis([])
    setSqlMap({})
    setEditingSQL({})
    setSelectedKpi('')

    const pgConn = (() => { try { return JSON.parse(sessionStorage.getItem('aurum_pg_conn') || 'null') } catch { return null } })()

    try {
      const res = await fetch(`${API}/gold/generate-kpi`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body:    JSON.stringify({ requirement, project_id: sessionStorage.getItem('aurum_project_id') || null, schema_info: schemaInfo, pg_conn: pgConn }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`)
      const d    = await res.json()
      const list = d.kpis || []
      if (list.length === 0) throw new Error('Empty KPI list returned')
      setKpis(list)
      const map = {}; list.forEach(k => { map[k.name] = k.sql || '' })
      setSqlMap(map)
      setSelectedKpi(list[0]?.name || '')
    } catch (err) {
      console.warn('[Gold] generate-kpi error:', err.message)
      setKpis([{ name: '⚠ Could not reach AI', status: 'Unavailable', sql: '' }])
    } finally {
      setGenerating(false)
    }
  }

  // ── Execute Gold ────────────────────────────────────────────────────────
  const handleExecute = async () => {
    setExecuting(true)
    const finalKpis = kpis.filter(k => k.status === 'Ready').map(k => ({ name: k.name, sql: editingSQL[k.name] ?? sqlMap[k.name] ?? '' }))
    const pgConn = (() => { try { return JSON.parse(sessionStorage.getItem('aurum_pg_conn') || 'null') } catch { return null } })()

    try {
      const res = await fetch(`${API}/gold/execute`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body:    JSON.stringify({ project_id: sessionStorage.getItem('aurum_project_id') || null, requirement, base_name: sessionStorage.getItem('aurum_base_name') || null, kpis: finalKpis, pg_conn: pgConn }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const d = await res.json()
      if (d.preview_rows?.length) { setPreview(d.preview_rows); setPreviewCols(Object.keys(d.preview_rows[0] || {})) }
      setGoldResult(d)
      sessionStorage.setItem('aurum_gold_result', JSON.stringify(d))
      setExecuted(true)
      // scroll to preview
      requestAnimationFrame(() =>
        setTimeout(() => document.getElementById('gold-preview-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
      )
    } catch (err) {
      console.warn('[Gold] execute error:', err.message)
      sessionStorage.setItem('aurum_gold_result', JSON.stringify({ requirement, kpis: finalKpis }))
      setExecuted(true)
    } finally {
      setExecuting(false)
    }
  }

  const [selectedGoldTable, setSelectedGoldTable] = useState(null)  // bare table name
  const [goldTablePreview,  setGoldTablePreview]  = useState([])
  const [goldTableCols,     setGoldTableCols]     = useState([])
  const [loadingPreview,    setLoadingPreview]    = useState(false)

  const handleGoldTableClick = async (tbl) => {
    if (selectedGoldTable === tbl) { setSelectedGoldTable(null); setGoldTablePreview([]); return }
    setSelectedGoldTable(tbl)
    setLoadingPreview(true)
    setGoldTablePreview([])
    try {
      const res = await fetch(`${API}/gold/preview?table=${encodeURIComponent(tbl)}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const d = await res.json()
      setGoldTablePreview(d.rows || [])
      setGoldTableCols(d.rows?.length ? Object.keys(d.rows[0]) : [])
    } catch (err) {
      setGoldTablePreview([])
    } finally {
      setLoadingPreview(false)
    }
  }
  const readyKpis = kpis.filter(k => k.status === 'Ready')
  const naKpis    = kpis.filter(k => k.status !== 'Ready')
  const currentSQL = editingSQL[selectedKpi] ?? sqlMap[selectedKpi] ?? ''

  return (
    <div style={{ display:'flex', width:'100%', height:'100vh', background:'#0d0e14', overflow:'hidden' }}>
      <Sidebar />
      <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>

        <TopNav
          tabs={TABS} activeTab="Gold Layer" activeColor="#f59e0b"
          onTabChange={t => navigate(`/project/${projectId}/${TAB_ROUTES[t]}`)}
          backLabel="Back to Silver"
          onBack={() => navigate(`/project/${projectId}/silver`)}
        />

        <main style={{ flex:1, padding:'18px 22px', overflow:'auto' }}>
          <h2 style={{ fontSize:22, fontWeight:700, color:'#e8e9f0', marginBottom:3 }}>Gold Layer</h2>
          <p style={{ color:'#8b8ca8', fontSize:13, marginBottom:16 }}>Generate business-ready Gold outputs from approved Silver data.</p>

          {/* 1. Business Requirement */}
          <div style={{ background:'#1a1b25', border:'1px solid #2a2b3d', borderRadius:10, padding:'14px 16px', marginBottom:14 }}>
            <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:10 }}>
              <div style={{ width:22, height:22, borderRadius:'50%', background:'#1e1f2e', border:'1px solid #2a2b3d', display:'flex', alignItems:'center', justifyContent:'center', fontSize:12, fontWeight:700, color:'#e8e9f0' }}>1</div>
              <span style={{ fontWeight:600, fontSize:13, color:'#e8e9f0' }}>Business Requirement</span>
            </div>
            <div style={{ display:'flex', gap:10 }}>
              <input value={requirement} onChange={e => setRequirement(e.target.value)}
                placeholder="e.g. I need an executive e-commerce dashboard showing GMV, top categories, refund rates…"
                style={{ flex:1, background:'#0d0e14', border:'1px solid #2a2b3d', borderRadius:8, padding:'9px 13px', color:'#e8e9f0', fontSize:13, outline:'none' }}
                onFocus={e => e.target.style.borderColor='#6366f1'} onBlur={e => e.target.style.borderColor='#2a2b3d'}
                onKeyDown={e => e.key==='Enter' && handleGenerateKPI()}
              />
              <button onClick={handleGenerateKPI} disabled={generating || !requirement.trim()}
                style={{ background:(generating||!requirement.trim())?'#2a2b3d':'#6366f1', color:(generating||!requirement.trim())?'#5a5b72':'#fff', border:'none', padding:'9px 18px', borderRadius:8, fontSize:13, fontWeight:600, cursor:(generating||!requirement.trim())?'default':'pointer', whiteSpace:'nowrap', display:'flex', alignItems:'center', gap:6 }}>
                {generating ? '⏳ Generating…' : '✦ Generate KPI Plan'}
              </button>
            </div>
          </div>

          {/* 2+3: KPI Plan | SQL */}
          {kpis.length > 0 && (
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:14, marginBottom:14 }}>

              {/* KPI Plan */}
              <div style={{ background:'#1a1b25', border:'1px solid #2a2b3d', borderRadius:10, overflow:'hidden' }}>
                <div style={{ padding:'11px 14px', borderBottom:'1px solid #2a2b3d', display:'flex', alignItems:'center', gap:8 }}>
                  <div style={{ width:22, height:22, borderRadius:'50%', background:'#1e1f2e', border:'1px solid #2a2b3d', display:'flex', alignItems:'center', justifyContent:'center', fontSize:12, fontWeight:700, color:'#e8e9f0' }}>2</div>
                  <span style={{ fontWeight:600, fontSize:13, color:'#e8e9f0' }}>KPI Plan</span>
                  <button onClick={() => { setKpis([]); setSqlMap({}); setEditingSQL({}); setSelectedKpi(''); setPreview([]); setPreviewCols([]) }}
                    style={{ marginLeft:'auto', background:'none', border:'1px solid #2a2b3d', borderRadius:6, padding:'3px 10px', fontSize:11, color:'#8b8ca8', cursor:'pointer' }}>Clear</button>
                </div>
                <div style={{ padding:'8px 10px', display:'flex', flexDirection:'column', gap:2 }}>
                  {kpis.map((kpi, i) => (
                    <div key={i} onClick={() => kpi.status==='Ready' && setSelectedKpi(kpi.name)}
                      style={{ display:'flex', alignItems:'center', gap:8, padding:'8px 10px', borderRadius:7, cursor:kpi.status==='Ready'?'pointer':'default', background:selectedKpi===kpi.name?'rgba(99,102,241,0.1)':'transparent' }}>
                      <span style={{ color:kpi.status==='Ready'?'#22c55e':'#f59e0b', fontSize:14 }}>{kpi.status==='Ready'?'✓':'⚠'}</span>
                      <span style={{ flex:1, fontSize:13, color:kpi.status==='Ready'?'#e8e9f0':'#8b8ca8' }}>
                        {kpi.name}{kpi.status!=='Ready' && <span style={{ fontSize:11, color:'#5a5b72' }}> — missing data</span>}
                      </span>
                      <span style={{ fontSize:10, padding:'2px 8px', borderRadius:20, fontWeight:600, background:kpi.status==='Ready'?'rgba(34,197,94,0.15)':'rgba(245,158,11,0.15)', color:kpi.status==='Ready'?'#22c55e':'#f59e0b', border:`1px solid ${kpi.status==='Ready'?'rgba(34,197,94,0.3)':'rgba(245,158,11,0.3)'}` }}>{kpi.status}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Generated SQL */}
              <div style={{ background:'#1a1b25', border:'1px solid #2a2b3d', borderRadius:10, overflow:'hidden', display:'flex', flexDirection:'column' }}>
                <div style={{ padding:'11px 14px', borderBottom:'1px solid #2a2b3d', display:'flex', alignItems:'center', gap:8 }}>
                  <div style={{ width:22, height:22, borderRadius:'50%', background:'#1e1f2e', border:'1px solid #2a2b3d', display:'flex', alignItems:'center', justifyContent:'center', fontSize:12, fontWeight:700, color:'#e8e9f0' }}>3</div>
                  <span style={{ fontWeight:600, fontSize:13, color:'#e8e9f0' }}>Generated SQL</span>
                  <span style={{ fontSize:11, color:'#5a5b72' }}>(click KPI to view/edit)</span>
                </div>
                <div style={{ borderBottom:'1px solid #1e1f2e', maxHeight:140, overflowY:'auto' }}>
                  {readyKpis.map(k => (
                    <div key={k.name} onClick={() => setSelectedKpi(k.name)}
                      style={{ display:'flex', alignItems:'center', padding:'7px 13px', cursor:'pointer', background:selectedKpi===k.name?'rgba(99,102,241,0.08)':'transparent', borderBottom:'1px solid #1e1f2e' }}>
                      <span style={{ fontSize:13, marginRight:8, color:'#6366f1', fontWeight:700, fontSize:11 }}>SQL</span>
                      <span style={{ flex:1, fontSize:12.5, color:'#e8e9f0' }}>{k.name}</span>
                      <span style={{ fontSize:11, color:'#6366f1' }}>View SQL</span>
                    </div>
                  ))}
                </div>
                {selectedKpi && sqlMap[selectedKpi] !== undefined ? (
                  <div style={{ flex:1, display:'flex', flexDirection:'column', padding:'10px 12px', gap:6 }}>
                    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                      <span style={{ fontSize:11, color:'#5a5b72' }}>{selectedKpi}</span>
                      <button onClick={() => setEditingSQL(p => ({ ...p, [selectedKpi]: sqlMap[selectedKpi] }))}
                        style={{ background:'none', border:'none', color:'#6366f1', fontSize:11, cursor:'pointer' }}>Reset</button>
                    </div>
                    <textarea value={currentSQL} onChange={e => setEditingSQL(p => ({ ...p, [selectedKpi]: e.target.value }))}
                      style={{ flex:1, minHeight:110, background:'#0d0e14', border:'1px solid #1e1f2e', borderRadius:7, padding:'10px 12px', color:'#818cf8', fontSize:11.5, fontFamily:'ui-monospace,Consolas,monospace', outline:'none', resize:'vertical', lineHeight:1.65 }} />
                  </div>
                ) : (
                  <div style={{ padding:'20px 14px', color:'#5a5b72', fontSize:12, textAlign:'center' }}>Click a KPI to view its SQL</div>
                )}
              </div>
            </div>
          )}

          {/* 4. Execute */}
          {kpis.length > 0 && (
            <div style={{ background:'#1a1b25', border:'1px solid #2a2b3d', borderRadius:10, padding:'14px 16px', marginBottom:14 }}>
              <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:10 }}>
                <div style={{ width:22, height:22, borderRadius:'50%', background:'#1e1f2e', border:'1px solid #2a2b3d', display:'flex', alignItems:'center', justifyContent:'center', fontSize:12, fontWeight:700, color:'#e8e9f0' }}>4</div>
                <span style={{ fontWeight:600, fontSize:13, color:'#e8e9f0' }}>Ready to Build</span>
              </div>
              <div style={{ display:'flex', alignItems:'center', gap:20 }}>
                <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                  <div>
                    <div style={{ fontSize:22, fontWeight:700, color:'#22c55e' }}>{readyKpis.length}</div>
                    <div style={{ fontSize:11, color:'#8b8ca8' }}>KPIs ready</div>
                  </div>
                  {naKpis.length > 0 && (
                    <><div style={{ width:1, height:36, background:'#2a2b3d' }}/><div style={{ display:'flex', alignItems:'center', gap:6 }}><span style={{ color:'#f59e0b' }}>⚠</span><div><div style={{ fontSize:22, fontWeight:700, color:'#f59e0b' }}>{naKpis.length}</div><div style={{ fontSize:11, color:'#8b8ca8' }}>unavailable</div></div></div></>
                  )}
                </div>
                <button onClick={handleExecute} disabled={executing || readyKpis.length === 0}
                  style={{ marginLeft:'auto', background:(executing||readyKpis.length===0)?'#2a2b3d':executed?'#22c55e':'#6366f1', color:(executing||readyKpis.length===0)?'#5a5b72':'#fff', border:'none', padding:'10px 20px', borderRadius:8, fontSize:13, fontWeight:600, cursor:(executing||readyKpis.length===0)?'default':'pointer', display:'flex', alignItems:'center', gap:6 }}>
                  {executing ? '⏳ Building…' : executed ? '✓ Built — rebuild?' : 'Approve & Build Gold'}
                </button>
              </div>
            </div>
          )}

          {/* 5. Gold preview — shown after execute */}
          {executed && goldResult && (
            <div id="gold-preview-section" style={{ marginTop:14 }}>
              {/* Tables created — clickable */}
              <div style={{ background:'#1a1b25', border:'1px solid #2a2b3d', borderTop:'2px solid #f59e0b', borderRadius:10, padding:'14px 16px', marginBottom:12 }}>
                <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:10 }}>
                  <div style={{ width:22, height:22, borderRadius:'50%', background:'#1e1f2e', border:'1px solid #2a2b3d', display:'flex', alignItems:'center', justifyContent:'center', fontSize:12, fontWeight:700, color:'#e8e9f0' }}>5</div>
                  <span style={{ fontWeight:600, fontSize:13, color:'#e8e9f0' }}>Gold Tables Created</span>
                  <span style={{ fontSize:11, color:'#22c55e', marginLeft:'auto' }}>{goldResult.tables_created?.length || 0} tables</span>
                </div>
                <div style={{ display:'flex', flexWrap:'wrap', gap:8 }}>
                  {(goldResult.tables_created || []).map(t => {
                    const isSelected = selectedGoldTable === t
                    return (
                      <button key={t} onClick={() => handleGoldTableClick(t)} style={{
                        background: isSelected ? 'rgba(245,158,11,0.2)' : 'rgba(245,158,11,0.08)',
                        border: `1px solid ${isSelected ? '#f59e0b' : 'rgba(245,158,11,0.25)'}`,
                        borderRadius:7, padding:'6px 14px', fontSize:12, color:'#f59e0b',
                        fontFamily:'ui-monospace,Consolas,monospace', cursor:'pointer',
                        transition:'all 0.15s',
                      }}>
                        gold.{t}
                      </button>
                    )
                  })}
                </div>
                <p style={{ fontSize:11, color:'#5a5b72', marginTop:10, marginBottom:0 }}>Click a table to preview its data</p>
              </div>

              {/* Table preview */}
              {selectedGoldTable && (
                <div style={{ background:'#1a1b25', border:'1px solid #2a2b3d', borderRadius:10, overflow:'hidden', marginBottom:12 }}>
                  <div style={{ padding:'10px 14px', borderBottom:'1px solid #2a2b3d', display:'flex', alignItems:'center', gap:8 }}>
                    <span style={{ fontWeight:600, fontSize:13, color:'#e8e9f0' }}>gold.{selectedGoldTable}</span>
                    <span style={{ fontSize:11, color:'#5a5b72', marginLeft:'auto' }}>First 5 rows</span>
                  </div>
                  {loadingPreview ? (
                    <div style={{ padding:'20px', textAlign:'center', color:'#5a5b72', fontSize:13 }}>Loading…</div>
                  ) : goldTablePreview.length === 0 ? (
                    <div style={{ padding:'20px', textAlign:'center', color:'#5a5b72', fontSize:13 }}>No rows returned — this KPI may be an aggregate with no matching data.</div>
                  ) : (
                    <div style={{ overflowX:'auto' }}>
                      <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
                        <thead>
                          <tr style={{ background:'#13141c' }}>
                            {goldTableCols.map(c => <th key={c} style={{ padding:'7px 13px', textAlign:'left', color:'#8b8ca8', fontWeight:600, fontSize:10.5, borderBottom:'1px solid #2a2b3d', whiteSpace:'nowrap' }}>{c}</th>)}
                          </tr>
                        </thead>
                        <tbody>
                          {goldTablePreview.map((row, i) => (
                            <tr key={i} style={{ borderBottom:'1px solid #1e1f2e' }}>
                              {goldTableCols.map(c => <td key={c} style={{ padding:'7px 13px', color:'#e8e9f0', whiteSpace:'nowrap' }}>{String(row[c] ?? '—')}</td>)}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </main>

        <div style={{ height:52, background:'#0f1018', borderTop:'1px solid #1e1f2e', display:'flex', alignItems:'center', justifyContent:'space-between', paddingInline:22, flexShrink:0 }}>
          <button onClick={() => navigate(`/project/${projectId}/silver`)} style={{ background:'#1e1f2e', color:'#e8e9f0', border:'1px solid #2a2b3d', padding:'8px 16px', borderRadius:8, fontSize:13, cursor:'pointer' }}>← Back to Silver</button>
          <p style={{ fontSize:11, color:'#5a5b72' }}>
            {!kpis.length ? 'Describe your requirement and generate a KPI plan.' : !executed ? 'Review the KPI SQL then click Approve & Build Gold.' : 'Gold tables created. Review the preview then generate your report.'}
          </p>
          <button onClick={() => navigate(`/project/${projectId}/report`)}
            disabled={!executed}
            style={{ background: executed ? '#22c55e' : '#1e1f2e', color: executed ? '#fff' : '#3a3b52', border: executed ? 'none' : '1px solid #2a2b3d', padding:'9px 20px', borderRadius:8, fontSize:13, fontWeight:600, cursor: executed ? 'pointer' : 'default', display:'flex', alignItems:'center', gap:6 }}>
            Generate Report →
          </button>
        </div>
      </div>
    </div>
  )
}
