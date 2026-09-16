import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Sidebar from '../components/Sidebar'
import TopNav from '../components/TopNav'

const TABS = ['Connect','Select','Configure Pipeline','Bronze Layer','Silver Layer','Gold Layer','Report']
const TAB_ROUTES = { Connect:'connect', Select:'select', 'Configure Pipeline':'pipeline-config', 'Bronze Layer':'bronze', 'Silver Layer':'silver', 'Gold Layer':'gold', Report:'report' }

export default function ReportPage() {
  const { projectId } = useParams()
  const navigate = useNavigate()

  // ── Read everything from sessionStorage ────────────────────────────────────
  const [data, setData] = useState(null)

  useEffect(() => {
    const get = k => sessionStorage.getItem(k)
    const getJ = (k, fallback) => { try { return JSON.parse(get(k) || 'null') ?? fallback } catch { return fallback } }

    const source      = get('aurum_source') || 'csv'

    // Resolve base_name safely — never use a stale product_sales_transactions value
    const rawBase = get('aurum_base_name') || get('aurum_dataset') || ''
    const projectName = get('aurum_project_name') || `Project ${projectId?.slice(0,8)}`
    const resolvedBase = (() => {
      if (rawBase && rawBase !== 'product_sales_transactions') return rawBase
      if (projectName && !projectName.startsWith('Project ')) {
        return projectName.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
      }
      const pgCfg = (() => { try { return JSON.parse(get('aurum_pg_conn') || 'null') } catch { return null } })()
      if (pgCfg?.database) return pgCfg.database.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
      return 'dataset'
    })()

    const baseName    = resolvedBase
    const bronzeTable = get('aurum_bronze_table') || `bronze.${baseName}_bronze`
    const selectedTables = getJ('aurum_selected_tables', [baseName])
    const bronzeSchema   = getJ('aurum_bronze_schema', [])

    // Silver results — read all executed tables from aurum_silver_results
    const silverResults  = getJ('aurum_silver_results', null)  // { [bronzeTable]: { bronze_rows, silver_rows, ... } }
    const silverResult   = getJ('aurum_silver_result', null)   // legacy single-table fallback

    // Aggregate across all executed silver tables
    let bronzeRows = 0, silverRows = 0, affected = 0, silverRules = [], silverTableNames = []
    if (silverResults && Object.keys(silverResults).length > 0) {
      for (const [bronzeTbl, res] of Object.entries(silverResults)) {
        bronzeRows  += res.bronze_rows ?? 0
        silverRows  += res.silver_rows ?? 0
        affected    += res.affected    ?? 0
        if (res.rules?.length) silverRules.push(...res.rules)
        // Derive the silver table name from the bronze table name
        const silverTbl = bronzeTbl.replace('_bronze', '_silver')
        silverTableNames.push(`silver.${silverTbl}`)
      }
    } else if (silverResult) {
      bronzeRows  = silverResult.bronze_rows ?? 0
      silverRows  = silverResult.silver_rows ?? 0
      affected    = silverResult.affected    ?? 0
      silverRules = silverResult.rules       ?? []
      silverTableNames = [`silver.${baseName}_silver`]
    }

    const pctChange = bronzeRows > 0
      ? `${((affected / bronzeRows) * -100).toFixed(2)}%`
      : '0.00%'

    // Gold results (set by GoldLayerPage after /gold/execute)
    const goldResult     = getJ('aurum_gold_result', null)
    const goldTables     = goldResult?.tables_created ?? []
    const goldPreview    = goldResult?.preview_rows ?? []
    const goldKpis       = goldResult?.kpis ?? []
    const goldKpiCount   = goldKpis.filter(k => k.status === 'Ready').length || goldTables.length

    setData({
      projectName,
      source,
      baseName,
      bronzeTable,
      selectedTables,
      bronzeSchema,
      bronzeRows,
      silverRows,
      silverRules,
      silverTableNames,
      affected,
      pctChange,
      goldTables,
      goldPreview,
      goldKpis,
      goldKpiCount,
      colCount: bronzeSchema.length,
    })
  }, [])

  if (!data) return (
    <div style={{ display:'flex', width:'100%', height:'100vh', background:'#0d0e14', alignItems:'center', justifyContent:'center' }}>
      <p style={{ color:'#5a5b72', fontSize:14 }}>Loading report…</p>
    </div>
  )

  const summaryCards = [
    { label: 'Rows Ingested',       value: data.bronzeRows  ? data.bronzeRows.toLocaleString()  : '—', color: '#e8e9f0' },
    { label: 'Rows Cleaned Out',    value: data.affected    ? data.affected.toLocaleString()     : '—', color: '#ef4444' },
    { label: 'Silver Rows',         value: data.silverRows  ? data.silverRows.toLocaleString()   : '—', color: '#818cf8' },
    { label: 'Cleaning Rules',      value: data.silverRules.length || '—',                               color: '#e8e9f0' },
    { label: 'KPIs Generated',      value: data.goldKpiCount || '—',                                      color: '#22c55e' },
    { label: 'Gold Tables Created', value: data.goldTables.length || '—',                                 color: '#f59e0b' },
    { label: 'Columns',             value: data.colCount || '—',                                           color: '#e8e9f0' },
  ]

  return (
    <div style={{ display:'flex', width:'100%', height:'100vh', background:'#0d0e14', overflow:'hidden' }}>
      <Sidebar />
      <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>

        <TopNav
          tabs={TABS} activeTab="Report" activeColor="#22c55e"
          onTabChange={t => navigate(`/project/${projectId}/${TAB_ROUTES[t]}`)}
          backLabel="Back to Gold"
          onBack={() => navigate(`/project/${projectId}/gold`)}
          rightContent={
            <>
              <button onClick={() => window.print()} style={{ background:'#1e1f2e', color:'#e8e9f0', border:'1px solid #2a2b3d', borderRadius:6, padding:'5px 12px', fontSize:12, cursor:'pointer' }}>↓ Export PDF</button>
              <button onClick={() => navigate('/')} style={{ background:'#6366f1', color:'#fff', border:'none', borderRadius:6, padding:'5px 12px', fontSize:12, cursor:'pointer', fontWeight:600 }}>← Home</button>
            </>
          }
        />

        <main style={{ flex:1, padding:'20px 26px', overflow:'auto' }}>

          {/* Header */}
          <div style={{ marginBottom:22 }}>
            <h2 style={{ fontSize:24, fontWeight:700, color:'#e8e9f0', marginBottom:4 }}>Pipeline Report</h2>
            <p style={{ color:'#8b8ca8', fontSize:13 }}>
              {data.projectName} · {new Date().toLocaleString()}
            </p>
            <div style={{ display:'flex', gap:8, marginTop:8, flexWrap:'wrap' }}>
              <span style={{ background:'#1e1f2e', border:'1px solid #2a2b3d', borderRadius:6, padding:'3px 10px', fontSize:11.5, color:'#8b8ca8' }}>
                Source: {data.source.toUpperCase()}
              </span>
              {data.selectedTables.map(t => (
                <span key={t} style={{ background:'#1e1f2e', border:'1px solid #2a2b3d', borderRadius:6, padding:'3px 10px', fontSize:11.5, color:'#8b8ca8' }}>
                  {t}
                </span>
              ))}
            </div>
          </div>

          {/* Summary cards */}
          <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:10, marginBottom:22 }}>
            {summaryCards.map(c => (
              <div key={c.label} style={{ background:'#1a1b25', border:'1px solid #2a2b3d', borderRadius:10, padding:'14px 16px' }}>
                <div style={{ fontSize:10, color:'#5a5b72', textTransform:'uppercase', letterSpacing:'0.08em', marginBottom:6 }}>{c.label}</div>
                <div style={{ fontSize:20, fontWeight:700, color:c.color }}>{c.value}</div>
              </div>
            ))}
          </div>

          {/* ── Pipeline Stages ── */}
          <h3 style={{ fontSize:15, fontWeight:600, color:'#e8e9f0', marginBottom:12 }}>Pipeline Stages</h3>
          <div style={{ display:'flex', flexDirection:'column', gap:12, marginBottom:22 }}>

            {/* Bronze */}
            <div style={{ background:'#1a1b25', border:'1px solid #2a2b3d', borderTop:'2px solid #f59e0b', borderRadius:10, padding:'16px 18px' }}>
              <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:10 }}>
                <div style={{ flex:1 }}>
                  <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                    <span style={{ fontWeight:700, fontSize:14.5, color:'#e8e9f0' }}>Ingestion → Bronze</span>
                  </div>
                  <p style={{ color:'#8b8ca8', fontSize:12.5, marginTop:3 }}>
                    Raw data copied from {data.source === 'csv' ? 'uploaded CSV' : 'PostgreSQL'} into{' '}
                    <code style={{ color:'#f59e0b', fontSize:11 }}>{data.bronzeTable}</code>.
                    Schema inferred automatically. No modifications applied.
                  </p>
                </div>
                <div style={{ display:'flex', gap:18, textAlign:'right', flexShrink:0 }}>
                  <div>
                    <div style={{ fontSize:16, fontWeight:700, color:'#e8e9f0' }}>{data.bronzeRows ? data.bronzeRows.toLocaleString() : '—'}</div>
                    <div style={{ fontSize:10, color:'#5a5b72' }}>rows in</div>
                  </div>
                  <div style={{ color:'#6366f1', fontSize:18, alignSelf:'center' }}>→</div>
                  <div>
                    <div style={{ fontSize:16, fontWeight:700, color:'#22c55e' }}>{data.bronzeRows ? data.bronzeRows.toLocaleString() : '—'}</div>
                    <div style={{ fontSize:10, color:'#5a5b72' }}>rows out</div>
                  </div>
                </div>
              </div>
              <div style={{ display:'flex', flexWrap:'wrap', gap:6 }}>
                {[
                  'Exact raw copy — no transformations',
                  `${data.colCount} columns detected`,
                  'Schema inferred from data types automatically',
                  'Bad data preserved — NULLs and outliers kept',
                ].map((d,i) => (
                  <span key={i} style={{ background:'#13141c', border:'1px solid #1e1f2e', borderRadius:6, padding:'4px 10px', fontSize:11.5, color:'#8b8ca8', display:'flex', alignItems:'center', gap:5 }}>
                    <span style={{ color:'#22c55e' }}>✓</span> {d}
                  </span>
                ))}
              </div>
            </div>

            {/* Silver */}
            <div style={{ background:'#1a1b25', border:'1px solid #2a2b3d', borderTop:'2px solid #818cf8', borderRadius:10, padding:'16px 18px' }}>
              <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:10 }}>
                <div style={{ flex:1 }}>
                  <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                    <span style={{ fontWeight:700, fontSize:14.5, color:'#e8e9f0' }}>Bronze → Silver</span>
                  </div>
                  <p style={{ color:'#8b8ca8', fontSize:12.5, marginTop:3 }}>
                    {data.silverRules.length} cleaning rule{data.silverRules.length !== 1 ? 's' : ''} applied via SQL CTE pipeline.
                    Output written to{' '}
                    {data.silverTableNames.length > 0
                      ? data.silverTableNames.map((t, i) => (
                          <code key={i} style={{ color:'#818cf8', fontSize:11, marginRight:6 }}>{t}</code>
                        ))
                      : <code style={{ color:'#818cf8', fontSize:11 }}>silver schema</code>
                    }.
                  </p>
                </div>
                <div style={{ display:'flex', gap:18, textAlign:'right', flexShrink:0 }}>
                  <div>
                    <div style={{ fontSize:16, fontWeight:700, color:'#e8e9f0' }}>{data.bronzeRows ? data.bronzeRows.toLocaleString() : '—'}</div>
                    <div style={{ fontSize:10, color:'#5a5b72' }}>rows in</div>
                  </div>
                  <div style={{ color:'#6366f1', fontSize:18, alignSelf:'center' }}>→</div>
                  <div>
                    <div style={{ fontSize:16, fontWeight:700, color:'#22c55e' }}>{data.silverRows ? data.silverRows.toLocaleString() : '—'}</div>
                    <div style={{ fontSize:10, color:'#5a5b72' }}>rows out</div>
                  </div>
                </div>
              </div>
              {/* Rules list */}
              {data.silverRules.length > 0 && (
                <div style={{ display:'flex', flexWrap:'wrap', gap:6, marginBottom:10 }}>
                  {data.silverRules.map((r, i) => (
                    <span key={i} style={{ background:'#13141c', border:'1px solid #1e1f2e', borderRadius:6, padding:'4px 10px', fontSize:11.5, color:'#8b8ca8', display:'flex', alignItems:'center', gap:5 }}>
                      <span style={{ color:'#818cf8' }}>SQL</span> {r}
                    </span>
                  ))}
                </div>
              )}
              <div style={{ display:'flex', gap:20, marginTop:4 }}>
                <span style={{ fontSize:12, color:'#5a5b72' }}>Rows removed: <span style={{ color:'#ef4444', fontWeight:600 }}>{data.affected?.toLocaleString() ?? '—'}</span></span>
                <span style={{ fontSize:12, color:'#5a5b72' }}>Δ change: <span style={{ color: data.affected > 0 ? '#ef4444' : '#22c55e', fontWeight:600 }}>{data.pctChange}</span></span>
                <span style={{ fontSize:12, color:'#5a5b72' }}>Rules applied: <span style={{ color:'#818cf8', fontWeight:600 }}>{data.silverRules.length}</span></span>
              </div>
            </div>

            {/* Gold */}
            <div style={{ background:'#1a1b25', border:'1px solid #2a2b3d', borderTop:'2px solid #f59e0b', borderRadius:10, padding:'16px 18px' }}>
              <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:10 }}>
                <div style={{ flex:1 }}>
                  <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                    <span style={{ fontWeight:700, fontSize:14.5, color:'#e8e9f0' }}>Silver → Gold</span>
                  </div>
                  <p style={{ color:'#8b8ca8', fontSize:12.5, marginTop:3 }}>
                    {data.goldKpiCount} business KPI{data.goldKpiCount !== 1 ? 's' : ''} computed from silver data.
                    Gold tables ready for BI tools and dashboards.
                  </p>
                </div>
                <div style={{ display:'flex', gap:18, textAlign:'right', flexShrink:0 }}>
                  <div>
                    <div style={{ fontSize:16, fontWeight:700, color:'#e8e9f0' }}>{data.silverRows ? data.silverRows.toLocaleString() : '—'}</div>
                    <div style={{ fontSize:10, color:'#5a5b72' }}>rows in</div>
                  </div>
                  <div style={{ color:'#6366f1', fontSize:18, alignSelf:'center' }}>→</div>
                  <div>
                    <div style={{ fontSize:16, fontWeight:700, color:'#f59e0b' }}>{data.goldKpiCount} KPIs</div>
                    <div style={{ fontSize:10, color:'#5a5b72' }}>created</div>
                  </div>
                </div>
              </div>
              {data.goldTables.length > 0 ? (
                <div style={{ display:'flex', flexWrap:'wrap', gap:6 }}>
                  {data.goldTables.map(t => (
                    <span key={t} style={{ background:'rgba(245,158,11,0.1)', border:'1px solid rgba(245,158,11,0.25)', borderRadius:6, padding:'4px 10px', fontSize:11.5, color:'#f59e0b' }}>
                      gold.{t}
                    </span>
                  ))}
                </div>
              ) : (
                <p style={{ fontSize:12, color:'#5a5b72' }}>No gold tables yet — run Gold Layer first.</p>
              )}
            </div>
          </div>

          {/* ── Gold Preview Table ── */}
          {data.goldPreview.length > 0 && (
            <div style={{ background:'#1a1b25', border:'1px solid #2a2b3d', borderRadius:10, overflow:'hidden', marginBottom:22 }}>
              <div style={{ padding:'12px 16px', borderBottom:'1px solid #2a2b3d', display:'flex', alignItems:'center', gap:8 }}>
                <span style={{ fontWeight:600, fontSize:13, color:'#e8e9f0' }}>Gold Layer Sample Output</span>
                <span style={{ fontSize:11, color:'#5a5b72', marginLeft:4 }}>First 5 rows from {data.goldTables[0] ? `gold.${data.goldTables[0]}` : 'first gold table'}</span>
              </div>
              <div style={{ overflowX:'auto' }}>
                <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
                  <thead>
                    <tr style={{ background:'#13141c' }}>
                      {Object.keys(data.goldPreview[0]).map(c => (
                        <th key={c} style={{ padding:'8px 14px', textAlign:'left', color:'#8b8ca8', fontWeight:600, fontSize:11, borderBottom:'1px solid #2a2b3d', whiteSpace:'nowrap' }}>{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.goldPreview.map((row, i) => (
                      <tr key={i} style={{ borderBottom:'1px solid #1e1f2e' }}>
                        {Object.values(row).map((v, j) => (
                          <td key={j} style={{ padding:'8px 14px', color:'#e8e9f0', whiteSpace:'nowrap' }}>{String(v ?? '—')}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── Table Name Reference ── */}
          <div style={{ background:'#1a1b25', border:'1px solid #2a2b3d', borderRadius:10, padding:'16px 18px', marginBottom:22 }}>
            <div style={{ fontSize:12, fontWeight:600, color:'#e8e9f0', marginBottom:12 }}>Database Table Reference</div>
            <div style={{ display:'grid', gridTemplateColumns:'80px 1fr', gap:'6px 16px', fontSize:12 }}>
              {/* Show all bronze tables (one per selected source table) */}
              {data.selectedTables.length > 1
                ? data.selectedTables.map(t => {
                    const bare = t.replace(/^bronze\./, '')
                    const bronzeName = bare.endsWith('_bronze') ? bare : `${bare}_bronze`
                    return (
                      <>
                        <span key={`lbl-${t}`} style={{ color:'#f59e0b', fontWeight:600 }}>Bronze</span>
                        <code key={`val-${t}`} style={{ color:'#e8e9f0' }}>bronze.{bronzeName}</code>
                      </>
                    )
                  })
                : <>
                    <span style={{ color:'#f59e0b', fontWeight:600 }}>Bronze</span>
                    <code style={{ color:'#e8e9f0' }}>{data.bronzeTable}</code>
                  </>
              }
              {data.silverTableNames.length > 0
                ? data.silverTableNames.map(t => (
                    <>
                      <span key={`lbl-${t}`} style={{ color:'#818cf8', fontWeight:600 }}>Silver</span>
                      <code key={`val-${t}`} style={{ color:'#e8e9f0' }}>{t}</code>
                    </>
                  ))
                : <>
                    <span style={{ color:'#818cf8', fontWeight:600 }}>Silver</span>
                    <code style={{ color:'#e8e9f0' }}>silver.{data.baseName}_silver</code>
                  </>
              }
              {data.goldTables.map(t => (
                <>
                  <span key={`lbl-${t}`} style={{ color:'#f59e0b', fontWeight:600 }}>Gold</span>
                  <code key={`val-${t}`} style={{ color:'#e8e9f0' }}>gold.{t}</code>
                </>
              ))}
            </div>
          </div>

          {/* ── Footer CTA ── */}
          <div style={{ background:'rgba(99,102,241,0.08)', border:'1px solid rgba(99,102,241,0.2)', borderRadius:10, padding:'16px 20px', display:'flex', alignItems:'center', justifyContent:'space-between' }}>
            <div>
              <div style={{ fontWeight:600, fontSize:14, color:'#e8e9f0', marginBottom:3 }}>Pipeline Complete</div>
              <div style={{ fontSize:12.5, color:'#8b8ca8' }}>Your Gold tables are ready. Connect a BI tool or export for downstream use.</div>
            </div>
            <div style={{ display:'flex', gap:10 }}>
              <button onClick={() => navigate(`/project/${projectId}/gold`)}
                style={{ background:'#1e1f2e', color:'#e8e9f0', border:'1px solid #2a2b3d', padding:'9px 18px', borderRadius:8, fontSize:13, cursor:'pointer' }}>
                ← Back to Gold
              </button>
              <button onClick={() => navigate('/')}
                style={{ background:'#6366f1', color:'#fff', border:'none', padding:'9px 18px', borderRadius:8, fontSize:13, fontWeight:600, cursor:'pointer' }}>
                ← Back to Dashboard
              </button>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
