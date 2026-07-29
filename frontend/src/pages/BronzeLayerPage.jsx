import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Sidebar from '../components/Sidebar'
import TopNav from '../components/TopNav'

const API = 'http://localhost:4000/api'
const TABS = ['Connect','Select','Configure Pipeline','Bronze Layer','Silver Layer','Gold Layer','Report']
const TAB_ROUTES = { Connect:'connect', Select:'select', 'Configure Pipeline':'pipeline-config', 'Bronze Layer':'bronze', 'Silver Layer':'silver', 'Gold Layer':'gold', Report:'report' }

// ── Table Nav Bar — shared between Bronze and Silver ─────────────────────────
export function TableNavBar({ tables, active, onSelect, accent = '#f59e0b' }) {
  if (!tables || tables.length <= 1) return null
  return (
    <div style={{
      background: '#0f1018', borderBottom: '1px solid #1e1f2e',
      display: 'flex', alignItems: 'center', gap: 2, paddingInline: 16,
      flexShrink: 0, overflowX: 'auto', height: 40,
    }}>
      <span style={{ fontSize: 10, color: '#5a5b72', letterSpacing: '0.1em', textTransform: 'uppercase', marginRight: 8, flexShrink: 0 }}>Tables</span>
      {tables.map(t => {
        const isActive = t === active
        return (
          <button key={t} onClick={() => onSelect(t)} style={{
            background: isActive ? `rgba(${accent === '#f59e0b' ? '245,158,11' : '99,102,241'},0.12)` : 'transparent',
            color: isActive ? accent : '#8b8ca8',
            border: 'none',
            borderBottom: isActive ? `2px solid ${accent}` : '2px solid transparent',
            borderTop: '2px solid transparent',
            padding: '0 12px', height: 40, fontSize: 12, fontWeight: isActive ? 600 : 400,
            cursor: 'pointer', whiteSpace: 'nowrap', flexShrink: 0,
            transition: 'all 0.12s',
          }}>
            {t}
          </button>
        )
      })}
    </div>
  )
}

export default function BronzeLayerPage() {
  const { projectId } = useParams()
  const navigate = useNavigate()

  const [rows,        setRows]        = useState([])
  const [schema,      setSchema]      = useState([])
  const [loading,     setLoading]     = useState(true)
  const [activeTable, setActiveTable] = useState('')   // bare name, e.g. "olist_orders_dataset_bronze"
  const [tableLabel,  setTableLabel]  = useState('')   // "bronze.olist_orders_dataset_bronze"
  const [selectedTables, setSelectedTables] = useState([]) // bare names filtered to session selection
  const [colCount,    setColCount]    = useState(0)
  const [rowCount,    setRowCount]    = useState('—')

  const loadPreview = (bareName) => {
    setLoading(true)
    setActiveTable(bareName)
    fetch(`${API}/bronze/preview?table=${encodeURIComponent(bareName)}`)
      .then(r => r.json())
      .then(d => {
        setLoading(false)
        if (d.rows?.length) {
          setRows(d.rows)
          setSchema(d.schema_cols || [])
          setColCount(d.col_count || Object.keys(d.rows[0] || {}).length)
          setRowCount((d.row_count || d.rows.length).toLocaleString())
          const fullName = d.bronze_table || `bronze.${bareName}`
          sessionStorage.setItem('aurum_bronze_table', fullName)
          setTableLabel(fullName)
          if (d.schema_cols?.length) {
            sessionStorage.setItem('aurum_bronze_schema', JSON.stringify(d.schema_cols))
          }
        } else {
          setRows([])
          setSchema([])
          setLoading(false)
        }
      })
      .catch(() => setLoading(false))
  }

  useEffect(() => {
    const storedBronze   = sessionStorage.getItem('aurum_bronze_table')
    const selectedRaw    = sessionStorage.getItem('aurum_selected_tables')
    const source         = sessionStorage.getItem('aurum_source') || 'csv'
    const dataset        = sessionStorage.getItem('aurum_dataset') || ''
    const selected       = selectedRaw ? JSON.parse(selectedRaw) : []

    fetch(`${API}/bronze/list`)
      .then(r => r.json())
      .then(allBronze => {
        if (!Array.isArray(allBronze) || allBronze.length === 0) {
          setLoading(false)
          return
        }

        // ── Filter bronze tables to only those from this session's selection ──
        // For postgres: selected = ["olist_orders_dataset", ...] → bronze = ["olist_orders_dataset_bronze", ...]
        // For csv: dataset = "my_file" → bronze = ["my_file_bronze"]
        let sessionTables = []

        if (selected.length > 0) {
          // Match: source table "foo" → bronze table "foo_bronze"
          sessionTables = selected
            .map(s => `${s}_bronze`)
            .filter(b => allBronze.includes(b))

          // Also try exact match (in case backend didn't append _bronze)
          if (sessionTables.length === 0) {
            sessionTables = selected.filter(s => allBronze.includes(s))
          }
        }

        if (sessionTables.length === 0 && dataset) {
          const safe  = dataset.replace(/[^a-z0-9]/gi, '_').toLowerCase()
          const match = allBronze.find(t => t === `${safe}_bronze` || t === safe || t.startsWith(safe))
          if (match) sessionTables = [match]
        }

        // Last resort: only fall back if nothing from selection matched
        if (sessionTables.length === 0) {
          sessionTables = [allBronze[allBronze.length - 1]]
        }

        setSelectedTables(sessionTables)

        // Determine which table to show first
        let target = null
        if (storedBronze) {
          const bare = storedBronze.replace('bronze.', '')
          if (sessionTables.includes(bare)) target = bare
        }
        if (!target) target = sessionTables[0]

        loadPreview(target)
      })
      .catch(() => setLoading(false))
  }, [])

  const handleContinueToSilver = () => {
    navigate(`/project/${projectId}/silver`)
  }

  const goTab = t => navigate(`/project/${projectId}/${TAB_ROUTES[t]}`)
  const cols  = rows.length > 0 ? Object.keys(rows[0]).filter(k => !['dup','isNull'].includes(k)) : []

  return (
    <div style={{ display:'flex', width:'100%', height:'100vh', background:'#0d0e14', overflow:'hidden' }}>
      <Sidebar />
      <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>

        <TopNav
          tabs={TABS} activeTab="Bronze Layer" activeColor="#f59e0b"
          onTabChange={goTab}
          backLabel="Back to Config"
          onBack={() => navigate(`/project/${projectId}/pipeline-config`)}
          rightContent={
            <span style={{ background:'#1e1f2e', color:'#8b8ca8', border:'1px solid #2a2b3d', fontSize:11, padding:'3px 8px', borderRadius:20 }}>{rowCount} rows · {colCount} cols</span>
          }
        />

        {/* ── Table nav bar (only when multiple tables selected) ── */}
        <TableNavBar
          tables={selectedTables}
          active={activeTable}
          onSelect={loadPreview}
          accent="#f59e0b"
        />

        <main style={{ flex:1, padding:'20px 24px', overflow:'auto' }}>
          <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:6, flexWrap:'wrap' }}>
            <h2 style={{ fontSize:22, fontWeight:700, color:'#e8e9f0' }}>Bronze Layer</h2>
            {selectedTables.length > 1 && (
              <span style={{ background:'rgba(245,158,11,0.1)', color:'#f59e0b', border:'1px solid rgba(245,158,11,0.3)', fontSize:11, padding:'3px 8px', borderRadius:20 }}>
                {selectedTables.length} tables
              </span>
            )}
          </div>
          <p style={{ color:'#8b8ca8', fontSize:13, marginBottom:18 }}>
            Raw data ingested exactly as-is from source. No modifications. Use the schema below when writing your Silver cleaning rules.
          </p>

          {/* Active table info bar */}
          <div style={{ background:'#1a1b25', border:'1px solid #2a2b3d', borderRadius:10, padding:'10px 16px', marginBottom:18, display:'flex', alignItems:'center', gap:12 }}>
            <span style={{ fontSize:11, color:'#5a5b72', flexShrink:0 }}>Viewing</span>
            <span style={{ fontSize:13, fontWeight:600, color:'#f59e0b' }}>{tableLabel || '—'}</span>
            <span style={{ fontSize:11, color:'#5a5b72' }}>{rowCount} rows · {colCount} columns</span>
            <div style={{ marginLeft:'auto', display:'flex', gap:6 }}>
              {cols.slice(0, 5).map(c => (
                <span key={c} style={{ background:'#13141c', border:'1px solid #2a2b3d', borderRadius:5, padding:'2px 8px', fontSize:11, color:'#8b8ca8' }}>{c}</span>
              ))}
              {cols.length > 5 && <span style={{ background:'#6366f1', borderRadius:5, padding:'2px 8px', fontSize:11, color:'#fff' }}>+{cols.length - 5}</span>}
            </div>
          </div>

          <div style={{ display:'grid', gridTemplateColumns:'1fr 300px', gap:20 }}>
            {/* Raw Data Table */}
            <div style={{ background:'#1a1b25', border:'1px solid #2a2b3d', borderRadius:10, overflow:'hidden' }}>
              <div style={{ padding:'12px 16px', borderBottom:'1px solid #2a2b3d', display:'flex', alignItems:'center', gap:10 }}>
                <div style={{ width:20, height:20, background:'rgba(245,158,11,0.2)', borderRadius:4, display:'flex', alignItems:'center', justifyContent:'center', fontSize:11, fontWeight:700, color:'#f59e0b' }}>1</div>
                <span style={{ fontWeight:600, fontSize:13, color:'#e8e9f0' }}>Raw Bronze Data</span>
                <span style={{ fontSize:11, color:'#5a5b72' }}>Exact copy · No modifications</span>
              </div>
              <div style={{ overflowX:'auto' }}>
                {loading ? (
                  <div style={{ padding:'32px', textAlign:'center', color:'#5a5b72', fontSize:13 }}>Loading…</div>
                ) : rows.length === 0 ? (
                  <div style={{ padding:'32px', textAlign:'center', color:'#5a5b72', fontSize:13 }}>
                    No data found in bronze table.<br/>
                    <span style={{ fontSize:12, color:'#3a3b52' }}>Upload a CSV or connect to PostgreSQL and ingest first.</span>
                  </div>
                ) : (
                  <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
                    <thead>
                      <tr style={{ background:'#13141c' }}>
                        {cols.map(c => (
                          <th key={c} style={{ padding:'8px 12px', textAlign:'left', color:'#8b8ca8', fontWeight:600, fontSize:10, letterSpacing:'0.08em', whiteSpace:'nowrap', borderBottom:'1px solid #2a2b3d' }}>
                            {c.toUpperCase()}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row, i) => (
                        <tr key={i} style={{ borderBottom:'1px solid #1e1f2e' }}>
                          {cols.map(c => (
                            <td key={c} style={{ padding:'8px 12px', whiteSpace:'nowrap', color: row[c] === null || row[c] === undefined ? '#ef4444' : '#e8e9f0', fontSize:12 }}>
                              {row[c] === null || row[c] === undefined ? <span style={{ fontStyle:'italic' }}>NULL</span> : String(row[c])}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
              <div style={{ padding:'8px 16px', borderTop:'1px solid #1e1f2e', display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                <span style={{ fontSize:11, color:'#5a5b72' }}>
                  <span style={{ color:'#ef4444' }}>■ Red = NULL</span> · <span style={{ color:'#f59e0b' }}>■ Amber = Duplicate</span>
                </span>
              </div>
            </div>

            {/* Information Schema */}
            <div style={{ background:'#1a1b25', border:'1px solid #2a2b3d', borderRadius:10, overflow:'hidden', position:'sticky', top:0 }}>
              <div style={{ padding:'12px 14px', borderBottom:'1px solid #2a2b3d', display:'flex', alignItems:'center', justifyContent:'space-between' }}>
                <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                  <div style={{ width:20, height:20, background:'rgba(99,102,241,0.2)', borderRadius:4, display:'flex', alignItems:'center', justifyContent:'center', fontSize:11, fontWeight:700, color:'#818cf8' }}>2</div>
                  <span style={{ fontWeight:600, fontSize:12, color:'#e8e9f0' }}>information_schema</span>
                </div>
                <span style={{ fontSize:10, color:'#5a5b72' }}>Column reference for Silver</span>
              </div>
              <div style={{ padding:'6px 14px 4px', fontSize:10, color:'#5a5b72' }}>INFORMATION_SCHEMA.COLUMNS</div>
              <div style={{ padding:'2px 14px 6px', fontSize:10, color:'#6366f1' }}>{tableLabel}</div>
              <div style={{ borderTop:'1px solid #1e1f2e' }}>
                <div style={{ display:'grid', gridTemplateColumns:'1fr 72px 56px', padding:'6px 14px', background:'#13141c' }}>
                  {['COLUMN','TYPE','NULLABLE'].map(h => (
                    <span key={h} style={{ fontSize:9.5, color:'#5a5b72', fontWeight:600, letterSpacing:'0.08em' }}>{h}</span>
                  ))}
                </div>
                {schema.length === 0 ? (
                  <div style={{ padding:'16px', color:'#5a5b72', fontSize:12, textAlign:'center' }}>Schema will appear after ingestion.</div>
                ) : schema.map((sc, i) => (
                  <div key={i} style={{ display:'grid', gridTemplateColumns:'1fr 72px 56px', padding:'6px 14px', borderTop:'1px solid #1e1f2e', alignItems:'center' }}>
                    <span style={{ fontSize:12, color:'#e8e9f0' }}>{sc.col}</span>
                    <span style={{ fontSize:10, background:'#13141c', border:'1px solid #2a2b3d', borderRadius:4, padding:'1px 5px', color:'#8b8ca8' }}>{sc.type}</span>
                    <span style={{ fontSize:10, color: sc.nullable === 'YES' ? '#f59e0b' : '#5a5b72' }}>{sc.nullable}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </main>

        {/* Footer */}
        <div style={{ height:52, background:'#0f1018', borderTop:'1px solid #1e1f2e', display:'flex', alignItems:'center', justifyContent:'space-between', paddingInline:24, flexShrink:0 }}>
          <div style={{ fontSize:12, color:'#5a5b72' }}>{tableLabel}</div>
          <button onClick={handleContinueToSilver} style={{
            background: '#6366f1', color:'#fff', border:'none',
            padding:'9px 22px', borderRadius:8, fontSize:13, fontWeight:600,
            cursor:'pointer', display:'flex', alignItems:'center', gap:6
          }}>
            Continue to Silver →
          </button>
        </div>
      </div>
    </div>
  )
}
