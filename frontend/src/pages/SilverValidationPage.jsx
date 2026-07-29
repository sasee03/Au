import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Sidebar from '../components/Sidebar'
import TopNav from '../components/TopNav'
import { TableNavBar } from './BronzeLayerPage'

const API = 'http://localhost:4000/api'
const TABS = ['Connect','Select','Configure Pipeline','Bronze Layer','Silver Layer','Gold Layer','Report']
const TAB_ROUTES = { Connect:'connect', Select:'select', 'Configure Pipeline':'pipeline-config', 'Bronze Layer':'bronze', 'Silver Layer':'silver', 'Gold Layer':'gold', Report:'report' }

const iconTrash = (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/>
    <path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/>
  </svg>
)
const iconDrag = (
  <svg width="14" height="14" viewBox="0 0 8 14" fill="none" stroke="#5a5b72" strokeWidth="1.5" strokeLinecap="round">
    <circle cx="2" cy="2" r="0.8" fill="#5a5b72"/><circle cx="6" cy="2" r="0.8" fill="#5a5b72"/>
    <circle cx="2" cy="7" r="0.8" fill="#5a5b72"/><circle cx="6" cy="7" r="0.8" fill="#5a5b72"/>
    <circle cx="2" cy="12" r="0.8" fill="#5a5b72"/><circle cx="6" cy="12" r="0.8" fill="#5a5b72"/>
  </svg>
)
const GHOST_RULE = 'e.g. Remove rows where customer_id is null, cast order_date to DATE…'

// ── Per-table state factory ───────────────────────────────────────────────────
const emptyTableState = () => ({
  rules: [], sqlMap: {}, editingSQL: {},
  approved: false, execResult: null,
  bronzeRows: [], previewRows: [], silverRows: [],
  previewCount: null,
})

function DataTable({ rows, label, accent = '#6366f1' }) {
  if (!rows || rows.length === 0) return null
  const cols = Object.keys(rows[0])
  return (
    <div style={{ background:'#1a1b25', border:`1px solid #2a2b3d`, borderTop:`2px solid ${accent}`, borderRadius:10, overflow:'hidden', marginBottom:16 }}>
      <div style={{ padding:'10px 14px', borderBottom:'1px solid #2a2b3d', display:'flex', alignItems:'center', gap:8 }}>
        <span style={{ fontWeight:600, fontSize:13, color:'#e8e9f0' }}>{label}</span>
        <span style={{ fontSize:11, color:'#5a5b72', marginLeft:'auto' }}>First {rows.length} rows</span>
      </div>
      <div style={{ overflowX:'auto' }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
          <thead>
            <tr style={{ background:'#13141c' }}>
              {cols.map(c => (
                <th key={c} style={{ padding:'7px 12px', textAlign:'left', color:'#8b8ca8', fontWeight:600, fontSize:10.5, borderBottom:'1px solid #2a2b3d', whiteSpace:'nowrap' }}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} style={{ borderBottom:'1px solid #1e1f2e' }}>
                {cols.map(c => (
                  <td key={c} style={{ padding:'7px 12px', color:'#e8e9f0', whiteSpace:'nowrap', maxWidth:220, overflow:'hidden', textOverflow:'ellipsis' }}>
                    {String(row[c] ?? '—')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function SilverValidationPage() {
  const { projectId } = useParams()
  const navigate = useNavigate()

  // ── Table list (one entry per selected source table) ─────────────────────
  // bronzeTables: ["olist_orders_dataset_bronze", "olist_order_items_dataset_bronze", ...]
  const [bronzeTables,  setBronzeTables]  = useState([])
  const [activeTable,   setActiveTable]   = useState('')  // bare bronze table name

  // ── Per-table state map: { [bareName]: tableState } ──────────────────────
  const [tableStates,   setTableStates]   = useState({})

  // ── Transient per-table UI state (not persisted across tab switches) ──────
  const [newRule,      setNewRule]      = useState('')
  const [generating,   setGenerating]   = useState(false)
  const [approving,    setApproving]    = useState(false)
  const [executing,    setExecuting]    = useState(false)
  const [ghostVisible, setGhostVisible] = useState(true)

  const pgConn = useCallback(() => {
    try { return JSON.parse(sessionStorage.getItem('aurum_pg_conn') || 'null') } catch { return null }
  }, [])

  // ── Helpers to read/write the active table's state slice ─────────────────
  const ts = tableStates[activeTable] || emptyTableState()

  const patchTs = (patch) =>
    setTableStates(prev => ({
      ...prev,
      [activeTable]: { ...(prev[activeTable] || emptyTableState()), ...patch }
    }))

  // Keep a ref to rules for async handlers
  const rulesRef = useRef(ts.rules)
  useEffect(() => { rulesRef.current = ts.rules }, [ts.rules])

  // ── Build bronze table list from sessionStorage on mount ─────────────────
  useEffect(() => {
    const selectedRaw = sessionStorage.getItem('aurum_selected_tables')
    const selected    = selectedRaw ? JSON.parse(selectedRaw) : []
    const dataset     = sessionStorage.getItem('aurum_dataset') || ''
    const storedBronze = sessionStorage.getItem('aurum_bronze_table') || ''

    fetch(`${API}/bronze/list`)
      .then(r => r.json())
      .then(allBronze => {
        if (!Array.isArray(allBronze)) return

        let sessionTables = []
        if (selected.length > 0) {
          sessionTables = selected.map(s => `${s}_bronze`).filter(b => allBronze.includes(b))
          if (!sessionTables.length) sessionTables = selected.filter(s => allBronze.includes(s))
        }
        if (!sessionTables.length && dataset) {
          const safe = dataset.replace(/[^a-z0-9]/gi, '_').toLowerCase()
          const match = allBronze.find(t => t === `${safe}_bronze` || t === safe)
          if (match) sessionTables = [match]
        }
        if (!sessionTables.length) {
          const bare = storedBronze.replace('bronze.', '')
          if (bare && allBronze.includes(bare)) sessionTables = [bare]
          else sessionTables = [allBronze[allBronze.length - 1]].filter(Boolean)
        }

        setBronzeTables(sessionTables)

        // Determine first active table
        let first = sessionTables[0]
        if (storedBronze) {
          const bare = storedBronze.replace('bronze.', '')
          if (sessionTables.includes(bare)) first = bare
        }
        setActiveTable(first)
      })
      .catch(() => {})
  }, [])

  // ── Load bronze preview whenever active table changes ────────────────────
  useEffect(() => {
    if (!activeTable) return
    // Update aurum_bronze_table so downstream pages (Silver exec, Gold) know the active table
    sessionStorage.setItem('aurum_bronze_table', `bronze.${activeTable}`)

    // Only fetch if we don't already have rows cached for this table
    const cached = tableStates[activeTable]?.bronzeRows
    if (cached?.length) return

    fetch(`${API}/bronze/preview?table=${encodeURIComponent(activeTable)}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.rows?.length) {
          patchTs({ bronzeRows: d.rows.slice(0, 5) })
        }
      })
      .catch(() => {})
  }, [activeTable])

  // ── Table switch ─────────────────────────────────────────────────────────
  const handleTableSelect = (bareName) => {
    setActiveTable(bareName)
    setNewRule('')
    setGhostVisible(true)
  }

  const tableLabel = activeTable ? `bronze.${activeTable}` : ''

  // ── Rule management ──────────────────────────────────────────────────────
  const addRule = () => {
    if (!newRule.trim()) return
    setGhostVisible(false)
    patchTs({
      rules: [...ts.rules, newRule.trim()],
      sqlMap: {}, editingSQL: {},
      approved: false, previewRows: [], previewCount: null,
    })
    setNewRule('')
  }

  const removeRule = (i) => {
    const reindex = (obj) => {
      const next = {}
      Object.entries(obj).forEach(([k, v]) => {
        const ki = parseInt(k)
        if (ki < i) next[ki] = v
        else if (ki > i) next[ki - 1] = v
      })
      return next
    }
    patchTs({
      rules: ts.rules.filter((_, idx) => idx !== i),
      sqlMap: reindex(ts.sqlMap),
      editingSQL: reindex(ts.editingSQL),
      approved: false, previewRows: [], previewCount: null,
    })
  }

  // ── Step 1: Generate SQL ──────────────────────────────────────────────────
  const handleGenerateSQL = async () => {
    const currentRules = ts.rules
    if (!currentRules.length) return
    setGenerating(true)
    patchTs({ sqlMap: {}, editingSQL: {}, approved: false, previewRows: [], previewCount: null })
    try {
      const res = await fetch(`${API}/silver/generate-sql`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          table: tableLabel,
          rules: currentRules,
          project_id: sessionStorage.getItem('aurum_project_id') || null,
          pg_conn: pgConn(),
        }),
      })
      if (!res.ok) { const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` })); throw new Error(err.detail || `HTTP ${res.status}`) }
      const d = await res.json()
      const items = d.sql_per_rule || []
      const newMap = {}
      currentRules.forEach((rule, i) => {
        const item = items[i] || items.find(it => it.rule === rule)
        newMap[i] = item?.sql || ''
      })
      patchTs({ sqlMap: newMap, editingSQL: {} })
    } catch (err) {
      alert(`AI model error: ${err.message}`)
    } finally {
      setGenerating(false)
    }
  }

  // ── Step 2: Approve (dry-run preview) ────────────────────────────────────
  const handleApprove = async () => {
    const currentRules = ts.rules
    const sqlList = currentRules.map((_, i) => ts.editingSQL[i] ?? ts.sqlMap[i] ?? '')
    if (sqlList.some(s => !s.trim())) { alert('Some rules have no SQL. Generate SQL first.'); return }
    setApproving(true)
    try {
      const res = await fetch(`${API}/silver/preview`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          table: tableLabel, rules: currentRules, sql_per_rule: sqlList,
          project_id: sessionStorage.getItem('aurum_project_id') || null,
          pg_conn: pgConn(),
        }),
      })
      if (!res.ok) { const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` })); throw new Error(err.detail || `HTTP ${res.status}`) }
      const d = await res.json()
      patchTs({ previewRows: d.preview_rows || [], previewCount: d.row_count ?? null, approved: true })
      requestAnimationFrame(() =>
        setTimeout(() => document.getElementById('silver-preview-section')?.scrollIntoView({ behavior:'smooth', block:'start' }), 50)
      )
    } catch (err) {
      alert(`Preview failed: ${err.message}`)
    } finally {
      setApproving(false)
    }
  }

  // ── Step 3: Execute ───────────────────────────────────────────────────────
  const handleExecute = async () => {
    const currentRules = ts.rules
    const finalSQL = currentRules.map((_, i) => ts.editingSQL[i] ?? ts.sqlMap[i] ?? '')
    setExecuting(true)
    try {
      const res = await fetch(`${API}/silver/execute`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          table: tableLabel, rules: currentRules, sql_per_rule: finalSQL,
          project_id: sessionStorage.getItem('aurum_project_id') || null,
          pg_conn: pgConn(),
        }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const d = await res.json()
      patchTs({ execResult: d, silverRows: (d.preview_rows || []).slice(0, 5) })
      // Persist per-table silver result
      const allResults = JSON.parse(sessionStorage.getItem('aurum_silver_results') || '{}')
      allResults[activeTable] = { bronze_rows: d.bronze_rows, silver_rows: d.silver_rows, affected: d.affected, pct_change: d.pct_change, rules: currentRules }
      sessionStorage.setItem('aurum_silver_results', JSON.stringify(allResults))
      // Also update legacy key for single-table compatibility
      sessionStorage.setItem('aurum_silver_result', JSON.stringify(allResults[activeTable]))
    } catch (err) {
      alert(`Execution failed: ${err.message}`)
    } finally {
      setExecuting(false)
    }
  }

  // ── All tables executed? ──────────────────────────────────────────────────
  const allExecuted = bronzeTables.length > 0 &&
    bronzeTables.every(t => tableStates[t]?.execResult != null)

  // Next table that hasn't been executed yet (for the "next table" button)
  const nextUnexecutedTable = bronzeTables.find(
    t => t !== activeTable && !tableStates[t]?.execResult
  ) || bronzeTables.find(t => t !== activeTable) || null

  const hasSql    = Object.keys(ts.sqlMap).length > 0 && ts.rules.length > 0
  const hasResult = ts.execResult != null

  const goTab = t => navigate(`/project/${projectId}/${TAB_ROUTES[t]}`)

  return (
    <div style={{ display:'flex', width:'100%', height:'100vh', background:'#0d0e14', overflow:'hidden' }}>
      <Sidebar />
      <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>

        <TopNav
          tabs={TABS} activeTab="Silver Layer" activeColor="#6366f1"
          onTabChange={goTab}
          backLabel="Back to Bronze"
          onBack={() => navigate(`/project/${projectId}/bronze`)}
        />

        {/* ── Table nav bar ── */}
        <TableNavBar
          tables={bronzeTables}
          active={activeTable}
          onSelect={handleTableSelect}
          accent="#818cf8"
        />

        <main style={{ flex:1, padding:'18px 22px', overflow:'auto' }}>
          <h2 style={{ fontSize:22, fontWeight:700, color:'#e8e9f0', marginBottom:3 }}>Silver Layer</h2>
          <p style={{ color:'#8b8ca8', fontSize:13, marginBottom:14 }}>
            Define cleaning rules per table, generate SQL, approve the dry-run preview, then execute to build each Silver table.
          </p>

          {/* Active table info bar */}
          <div style={{ background:'#1a1b25', border:'1px solid #2a2b3d', borderRadius:10, padding:'10px 16px', marginBottom:16, display:'flex', alignItems:'center', gap:10 }}>
            <span style={{ fontSize:11, color:'#5a5b72' }}>Source</span>
            <span style={{ fontSize:13, fontWeight:600, color:'#f59e0b' }}>{tableLabel || '—'}</span>
            {hasResult && (
              <span style={{ fontSize:11, color:'#5a5b72', marginLeft:'auto' }}>
                {ts.execResult.bronze_rows?.toLocaleString()} → {ts.execResult.silver_rows?.toLocaleString()} rows · {ts.execResult.pct_change}
              </span>
            )}
            {bronzeTables.length > 1 && (
              <span style={{ marginLeft: hasResult ? 0 : 'auto', fontSize:11,
                color: allExecuted ? '#22c55e' : '#5a5b72',
                background: allExecuted ? 'rgba(34,197,94,0.1)' : '#13141c',
                border: `1px solid ${allExecuted ? 'rgba(34,197,94,0.3)' : '#2a2b3d'}`,
                borderRadius:5, padding:'2px 8px' }}>
                {bronzeTables.filter(t => tableStates[t]?.execResult).length}/{bronzeTables.length} tables executed
              </span>
            )}
          </div>

          {/* ── Rules | SQL grid ── */}
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16, marginBottom:16 }}>

            {/* Cleaning Rules */}
            <div style={{ background:'#1a1b25', border:'1px solid #2a2b3d', borderRadius:10, overflow:'hidden', display:'flex', flexDirection:'column' }}>
              <div style={{ padding:'11px 14px', borderBottom:'1px solid #2a2b3d', display:'flex', alignItems:'center', gap:8 }}>
                <div style={{ width:20, height:20, background:'rgba(99,102,241,0.2)', borderRadius:4, display:'flex', alignItems:'center', justifyContent:'center', fontSize:11, fontWeight:700, color:'#818cf8' }}>1</div>
                <span style={{ fontWeight:600, fontSize:13, color:'#e8e9f0' }}>Cleaning Rules</span>
                <span style={{ fontSize:11, color:'#5a5b72' }}>(Ordered)</span>
                {ts.rules.length > 0 && <span style={{ marginLeft:'auto', fontSize:11, color:'#5a5b72' }}>{ts.rules.length} rule{ts.rules.length !== 1 ? 's' : ''}</span>}
              </div>
              <div style={{ padding:'8px 12px', display:'flex', flexDirection:'column', gap:4, flex:1 }}>
                {ts.rules.length === 0 && ghostVisible && (
                  <div onClick={() => setGhostVisible(false)}
                    style={{ display:'flex', alignItems:'center', gap:8, padding:'9px 10px', background:'#0d0e14', borderRadius:7, border:'1px dashed #2a2b3d', cursor:'pointer', opacity:0.5 }}>
                    <span style={{ width:18, height:18, borderRadius:'50%', background:'#1e1f2e', display:'flex', alignItems:'center', justifyContent:'center', fontSize:10, color:'#5a5b72', flexShrink:0 }}>1</span>
                    <span style={{ flex:1, fontSize:12, color:'#5a5b72', fontStyle:'italic' }}>{GHOST_RULE}</span>
                  </div>
                )}
                {ts.rules.map((rule, i) => (
                  <div key={i} style={{ display:'flex', alignItems:'center', gap:8, padding:'8px 10px', background:'#13141c', borderRadius:7 }}>
                    <span style={{ cursor:'grab', flexShrink:0 }}>{iconDrag}</span>
                    <span style={{ width:18, height:18, borderRadius:'50%', background:'#1e1f2e', display:'flex', alignItems:'center', justifyContent:'center', fontSize:10, color:'#8b8ca8', flexShrink:0 }}>{i+1}</span>
                    <span style={{ flex:1, fontSize:12.5, color:'#e8e9f0' }}>{rule}</span>
                    <button onClick={() => removeRule(i)} style={{ background:'none', border:'none', color:'#5a5b72', cursor:'pointer', padding:2 }}>{iconTrash}</button>
                  </div>
                ))}
                <div style={{ display:'flex', gap:6, marginTop:4 }}>
                  <input value={newRule}
                    onChange={e => { setNewRule(e.target.value); setGhostVisible(false) }}
                    onKeyDown={e => e.key === 'Enter' && addRule()}
                    placeholder="Describe a cleaning rule in plain English…"
                    style={{ flex:1, background:'#0d0e14', border:'1px solid #2a2b3d', borderRadius:7, padding:'7px 10px', color:'#e8e9f0', fontSize:12.5, outline:'none' }}
                    onFocus={e => { e.target.style.borderColor = '#6366f1'; setGhostVisible(false) }}
                    onBlur={e => e.target.style.borderColor = '#2a2b3d'}
                  />
                  <button onClick={addRule} style={{ background:'#6366f1', color:'#fff', border:'none', borderRadius:7, padding:'7px 12px', fontSize:16, cursor:'pointer', fontWeight:600 }}>+</button>
                </div>
              </div>
              <div style={{ padding:'12px 14px', borderTop:'1px solid #1e1f2e' }}>
                <button onClick={handleGenerateSQL} disabled={generating || !ts.rules.length}
                  style={{ width:'100%', background:(generating||!ts.rules.length)?'#1a1b25':'rgba(99,102,241,0.12)', color:(generating||!ts.rules.length)?'#3a3b52':'#818cf8', border:'1px solid rgba(99,102,241,0.3)', borderRadius:8, padding:'9px', fontSize:13, fontWeight:600, cursor:(generating||!ts.rules.length)?'default':'pointer', display:'flex', alignItems:'center', justifyContent:'center', gap:6 }}>
                  {generating ? '⏳ Generating SQL…' : '✦ Generate SQL'}
                </button>
              </div>
            </div>

            {/* Generated SQL */}
            <div style={{ background:'#1a1b25', border:'1px solid #2a2b3d', borderRadius:10, overflow:'hidden', display:'flex', flexDirection:'column' }}>
              <div style={{ padding:'11px 14px', borderBottom:'1px solid #2a2b3d', display:'flex', alignItems:'center', gap:8 }}>
                <div style={{ width:20, height:20, background:'rgba(34,197,94,0.2)', borderRadius:4, display:'flex', alignItems:'center', justifyContent:'center', fontSize:11, fontWeight:700, color:'#22c55e' }}>2</div>
                <span style={{ fontWeight:600, fontSize:13, color:'#e8e9f0' }}>Generated SQL</span>
                <span style={{ fontSize:11, color:'#5a5b72' }}>(click to edit)</span>
                {hasSql && <span style={{ marginLeft:'auto', fontSize:11, color:'#22c55e' }}>All rules ready</span>}
              </div>
              <div style={{ padding:'8px 12px', display:'flex', flexDirection:'column', gap:6, flex:1, overflowY:'auto' }}>
                {!hasSql && <p style={{ color:'#5a5b72', fontSize:12, padding:'12px 4px' }}>Add rules then click "Generate SQL".</p>}
                {ts.rules.map((_, i) => {
                  const sql = ts.editingSQL[i] ?? ts.sqlMap[i] ?? ''
                  const hasThisSQL = ts.sqlMap[i] !== undefined
                  return (
                    <div key={i} style={{ background:'#13141c', borderRadius:7, overflow:'hidden', border:'1px solid #1e1f2e' }}>
                      {hasThisSQL && (
                        <textarea value={sql}
                          onChange={e => patchTs({ editingSQL: { ...ts.editingSQL, [i]: e.target.value } })}
                          style={{ width:'100%', background:'#0d0e14', border:'none', color:'#818cf8', fontSize:11.5, fontFamily:'ui-monospace,Consolas,monospace', padding:'10px 12px', outline:'none', resize:'vertical', minHeight:56, lineHeight:1.6, boxSizing:'border-box' }} />
                      )}
                    </div>
                  )
                })}
              </div>
              <div style={{ padding:'8px 12px', borderTop:'1px solid #1e1f2e' }}>
                <p style={{ fontSize:11, color:'#5a5b72' }}>Steps run in order as a single CTE pipeline.</p>
              </div>
            </div>
          </div>

          {/* ── Preview section ── */}
          <div id="silver-preview-section">
            {/* DEFAULT: bronze rows */}
            {!ts.approved && !hasResult && (
              <DataTable rows={ts.bronzeRows} label={`Bronze — ${tableLabel}`} accent="#f59e0b" />
            )}

            {/* AFTER APPROVE: SQL dry-run */}
            {ts.approved && !hasResult && (
              <div>
                <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:10 }}>
                  <span style={{ fontSize:12, fontWeight:600, color:'#818cf8' }}>Preview after cleaning rules applied</span>
                  {ts.previewCount !== null && (
                    <span style={{ fontSize:11, color:'#5a5b72' }}>{ts.previewCount.toLocaleString()} rows expected in Silver</span>
                  )}
                  <span style={{ marginLeft:'auto', fontSize:11, color:'#22c55e', background:'rgba(34,197,94,0.1)', border:'1px solid rgba(34,197,94,0.25)', borderRadius:5, padding:'2px 8px' }}>dry run — no DB changes</span>
                </div>
                <DataTable rows={ts.previewRows} label={`SQL-applied preview — ${tableLabel}`} accent="#818cf8" />
              </div>
            )}

            {/* AFTER EXECUTE: stats + silver rows */}
            {hasResult && (
              <>
                <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:10, marginBottom:16 }}>
                  {[
                    { label:'Bronze Rows',  value: ts.execResult.bronze_rows?.toLocaleString() ?? '—', color:'#e8e9f0' },
                    { label:'Silver Rows',  value: ts.execResult.silver_rows?.toLocaleString() ?? '—', color:'#818cf8' },
                    { label:'Rows Removed', value: ts.execResult.affected?.toLocaleString()    ?? '—', color:'#ef4444' },
                    { label:'Change',       value: ts.execResult.pct_change ?? '—',                    color:'#f59e0b' },
                  ].map(s => (
                    <div key={s.label} style={{ background:'#1a1b25', border:'1px solid #2a2b3d', borderRadius:10, padding:'14px 16px', textAlign:'center' }}>
                      <div style={{ fontSize:22, fontWeight:700, color:s.color }}>{s.value}</div>
                      <div style={{ fontSize:10, color:'#8b8ca8', marginTop:4 }}>{s.label}</div>
                    </div>
                  ))}
                </div>
                <DataTable rows={ts.silverRows} label={`Silver — ${activeTable.replace('_bronze','_silver')}`} accent="#22c55e" />
              </>
            )}
          </div>
        </main>

        {/* ── Footer ── */}
        <div style={{ height:60, background:'#0f1018', borderTop:'1px solid #1e1f2e', display:'flex', alignItems:'center', justifyContent:'space-between', paddingInline:22, flexShrink:0 }}>
          <button onClick={() => navigate(`/project/${projectId}/bronze`)}
            style={{ background:'#1e1f2e', color:'#e8e9f0', border:'1px solid #2a2b3d', padding:'8px 16px', borderRadius:8, fontSize:13, cursor:'pointer' }}>
            ← Back to Bronze
          </button>
          <p style={{ fontSize:11, color:'#5a5b72' }}>
            {!hasSql
              ? 'Add rules and generate SQL to proceed.'
              : !ts.approved
              ? 'Review SQL then Approve.'
              : !hasResult
              ? 'SQL preview shown — click Execute to write to Silver.'
              : allExecuted
              ? 'All tables executed. Proceed to Gold.'
              : 'Table executed. Process remaining tables or continue to Gold.'}
          </p>
          <div style={{ display:'flex', gap:10 }}>
            <button onClick={handleApprove} disabled={!hasSql || ts.approved || approving}
              style={{ background:(!hasSql||ts.approved||approving)?'#1a1b25':'rgba(99,102,241,0.15)', color:(!hasSql||ts.approved||approving)?'#3a3b52':'#818cf8', border:`1px solid ${(!hasSql||ts.approved||approving)?'#2a2b3d':'rgba(99,102,241,0.4)'}`, padding:'9px 20px', borderRadius:8, fontSize:13, fontWeight:600, cursor:(!hasSql||ts.approved||approving)?'default':'pointer', display:'flex', alignItems:'center', gap:6 }}>
              {approving ? '⏳ Previewing…' : ts.approved ? '✓ Approved' : 'Approve'}
            </button>
            <button
              onClick={
                allExecuted
                  ? () => navigate(`/project/${projectId}/gold`)
                  : hasResult && nextUnexecutedTable
                  ? () => handleTableSelect(nextUnexecutedTable)
                  : handleExecute
              }
              disabled={!ts.approved || executing}
              style={{ background:(!ts.approved||executing)?'#2a2b3d':allExecuted?'#22c55e':hasResult?'#818cf8':'#6366f1', color:(!ts.approved||executing)?'#5a5b72':'#fff', border:'none', padding:'9px 20px', borderRadius:8, fontSize:13, fontWeight:600, cursor:(!ts.approved||executing)?'default':'pointer', display:'flex', alignItems:'center', gap:6 }}>
              {executing ? '⏳ Executing…' : allExecuted ? '→ Continue to Gold' : hasResult && nextUnexecutedTable ? `→ Next: ${nextUnexecutedTable.replace('_bronze','')}` : '▶ Execute'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
