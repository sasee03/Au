import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Sidebar from '../components/Sidebar'
import TopNav from '../components/TopNav'

const API = 'http://localhost:4000/api'
const TABS = ['Connect','Select','Configure Pipeline','Bronze Layer','Silver Layer','Gold Layer','Report']
const TAB_ROUTES = { Connect:'connect', Select:'select', 'Configure Pipeline':'pipeline-config', 'Bronze Layer':'bronze', 'Silver Layer':'silver', 'Gold Layer':'gold', Report:'report' }

export default function DatasetExplorerPage() {
  const { projectId } = useParams()
  const navigate = useNavigate()

  const source = sessionStorage.getItem('aurum_source') || 'csv'
  const pgConn = (() => {
    try { return JSON.parse(sessionStorage.getItem('aurum_pg_conn') || '{}') }
    catch { return {} }
  })()

  const [tables,        setTables]       = useState([])
  const [checked,       setChecked]      = useState({})
  const [search,        setSearch]       = useState('')
  const [loading,       setLoading]      = useState(false)
  const [schemaTree,    setSchemaTree]   = useState([]) // [{ schema, tables:[name] }]
  const [activeSchema,  setActiveSchema] = useState(pgConn.schema || 'public')
  const [expandedSchemas, setExpanded]  = useState({})

  // ── Load schema tree + table list ─────────────────────────────────────────
  useEffect(() => {
    if (source !== 'postgres') {
      // CSV flow: show just the uploaded dataset
      const name = sessionStorage.getItem('aurum_dataset') || 'dataset'
      setTables([{ name, owner: 'CSV upload', time: 'just now', rows: '—', cols: '—', size: '—' }])
      setChecked({ [name]: true })
      return
    }

    // Postgres: load full schema tree first, then load tables for active schema
    setLoading(true)

    // Load schema tree
    fetch(`${API}/postgres/tree`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(pgConn),
    })
      .then(r => r.json())
      .then(tree => {
        if (Array.isArray(tree) && tree.length > 0) {
          setSchemaTree(tree)
          // Expand the connected schema by default
          const initial = {}
          tree.forEach(s => { initial[s.schema] = true })
          setExpanded(initial)
        }
      })
      .catch(() => {})

    // Load tables for the active schema
    loadTablesForSchema(activeSchema)
  }, [])

  const loadTablesForSchema = (schema) => {
    setLoading(true)
    const body = { ...pgConn, schema }
    fetch(`${API}/postgres/tables`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then(r => r.json())
      .then(d => {
        const list = Array.isArray(d) && d.length > 0 ? d : []
        setTables(list)
        // Pre-check all tables
        setChecked(Object.fromEntries(list.map(t => [t.name, false])))
      })
      .catch(() => setTables([]))
      .finally(() => setLoading(false))
  }

  const handleSchemaClick = (schema) => {
    setActiveSchema(schema)
    // Update sessionStorage so downstream pages use the right schema
    const updated = { ...pgConn, schema }
    sessionStorage.setItem('aurum_pg_conn', JSON.stringify(updated))
    loadTablesForSchema(schema)
  }

  const toggle = name => setChecked(p => ({ ...p, [name]: !p[name] }))

  const handleContinue = () => {
    const selected = tables.filter(t => checked[t.name]).map(t => t.name)
    if (selected.length === 0) return
    sessionStorage.setItem('aurum_selected_tables', JSON.stringify(selected))
    // Clear stale bronze table pointer from any previous session so BronzeLayerPage
    // doesn't fall back to an old table when the source or selection has changed
    sessionStorage.removeItem('aurum_bronze_table')
    sessionStorage.removeItem('aurum_bronze_schema')
    // Update pg_conn with active schema
    if (source === 'postgres') {
      const updated = { ...pgConn, schema: activeSchema }
      sessionStorage.setItem('aurum_pg_conn', JSON.stringify(updated))
    }
    navigate(`/project/${projectId}/pipeline-config`)
  }

  const filtered = tables.filter(t =>
    t.name.toLowerCase().includes(search.toLowerCase())
  )

  const selectedCount = Object.values(checked).filter(Boolean).length

  return (
    <div style={{ display: 'flex', width: '100%', height: '100vh', background: '#0d0e14', overflow: 'hidden' }}>
      <Sidebar />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        <TopNav
          tabs={TABS} activeTab="Select" activeColor="#6366f1"
          onTabChange={t => navigate(`/project/${projectId}/${TAB_ROUTES[t]}`)}
        />

        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

          {/* ── Left tree panel (Postgres only) ── */}
          {source === 'postgres' && (
            <aside style={{ width: 200, borderRight: '1px solid #1e1f2e', display: 'flex', flexDirection: 'column', flexShrink: 0, overflow: 'hidden' }}>
              {/* Connection info */}
              <div style={{ padding: '12px 14px', borderBottom: '1px solid #1e1f2e', flexShrink: 0 }}>
                <div style={{ fontSize: 10, letterSpacing: '0.12em', color: '#5a5b72', textTransform: 'uppercase', marginBottom: 4 }}>Connected</div>
                <div style={{ fontSize: 12.5, color: '#6366f1', fontWeight: 600, marginBottom: 2 }}>{pgConn.database || 'database'}</div>
                <div style={{ fontSize: 11, color: '#5a5b72' }}>{pgConn.host || 'localhost'}:{pgConn.port || '5432'}</div>
                <div style={{ fontSize: 11, color: '#5a5b72', marginTop: 2 }}>
                  Active: <span style={{ color: '#818cf8' }}>{activeSchema}</span>
                </div>
              </div>

              {/* Real schema tree */}
              <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
                {schemaTree.length === 0 && (
                  <div style={{ padding: '12px 14px', fontSize: 12, color: '#5a5b72' }}>Loading schemas…</div>
                )}
                {schemaTree.map(s => (
                  <div key={s.schema}>
                    {/* Schema row */}
                    <div
                      onClick={() => {
                        setExpanded(p => ({ ...p, [s.schema]: !p[s.schema] }))
                        handleSchemaClick(s.schema)
                      }}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        padding: '6px 14px', cursor: 'pointer',
                        background: activeSchema === s.schema ? 'rgba(99,102,241,0.12)' : 'transparent',
                        fontSize: 13, fontWeight: 500,
                        color: activeSchema === s.schema ? '#818cf8' : '#8b8ca8',
                      }}
                    >
                      <span style={{ fontSize: 9, color: '#f59e0b' }}>
                        {expandedSchemas[s.schema] ? '▼' : '▶'}
                      </span>
                      {s.schema}
                      <span style={{ marginLeft: 'auto', fontSize: 10, color: '#5a5b72' }}>{s.tables.length}</span>
                    </div>
                    {/* Table rows */}
                    {expandedSchemas[s.schema] && s.tables.map(tbl => (
                      <div
                        key={tbl}
                        onClick={() => {
                          handleSchemaClick(s.schema)
                          // highlight this table
                        }}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 6,
                          padding: '4px 14px 4px 28px', cursor: 'pointer',
                          fontSize: 12.5, color: '#6b7280',
                        }}
                        onMouseEnter={e => e.currentTarget.style.color = '#a5b4fc'}
                        onMouseLeave={e => e.currentTarget.style.color = '#6b7280'}
                      >
                        <span style={{ fontSize: 9, color: '#3b82f6' }}>▶</span>
                        {tbl}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </aside>
          )}

          {/* ── Main table list ── */}
          <main style={{ flex: 1, padding: 28, overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
            <h2 style={{ fontSize: 20, fontWeight: 700, color: '#e8e9f0', marginBottom: 4 }}>Dataset Explorer</h2>
            <p style={{ color: '#8b8ca8', fontSize: 13, marginBottom: 20 }}>
              {source === 'postgres'
                ? `Select tables from schema "${activeSchema}" for AURUM to validate this run.`
                : 'Select datasets for AURUM to validate this run.'}
            </p>

            {loading && (
              <div style={{ color: '#5a5b72', fontSize: 13, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ display: 'inline-block', width: 12, height: 12, border: '2px solid #6366f1', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
                Loading tables from {activeSchema}…
              </div>
            )}

            {/* Search */}
            {tables.length > 0 && (
              <input
                placeholder="Search tables..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                style={{
                  width: '100%', background: '#1a1b25', border: '1px solid #2a2b3d',
                  borderRadius: 8, padding: '10px 14px', color: '#e8e9f0', fontSize: 13,
                  outline: 'none', marginBottom: 12,
                }}
                onFocus={e => e.target.style.borderColor = '#6366f1'}
                onBlur={e => e.target.style.borderColor = '#2a2b3d'}
              />
            )}

            {/* Empty state */}
            {!loading && tables.length === 0 && (
              <div style={{ color: '#5a5b72', fontSize: 13, padding: '24px 0' }}>
                No tables found in schema <strong style={{ color: '#818cf8' }}>{activeSchema}</strong>.
                {source === 'postgres' && ' Click a schema in the tree on the left to browse its tables.'}
              </div>
            )}

            {/* Table list */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1 }}>
              {filtered.map(t => (
                <div key={t.name} style={{
                  display: 'flex', alignItems: 'center', padding: '12px 16px',
                  background: '#1a1b25', borderRadius: 8, cursor: 'pointer', gap: 12,
                  border: `1px solid ${checked[t.name] ? 'rgba(99,102,241,0.35)' : '#1e1f2e'}`,
                  transition: 'border-color 0.15s',
                }}
                  onMouseEnter={e => { if (!checked[t.name]) e.currentTarget.style.borderColor = '#2a2b3d' }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = checked[t.name] ? 'rgba(99,102,241,0.35)' : '#1e1f2e' }}
                  onClick={() => toggle(t.name)}
                >
                  <input
                    type="checkbox"
                    checked={checked[t.name] || false}
                    onChange={() => toggle(t.name)}
                    onClick={e => e.stopPropagation()}
                    style={{ width: 15, height: 15, accentColor: '#6366f1', cursor: 'pointer', flexShrink: 0 }}
                  />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: 13.5, color: '#e8e9f0' }}>{t.name}</div>
                    <div style={{ fontSize: 11.5, color: '#5a5b72', marginTop: 2 }}>
                      {t.owner} · {t.time}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 20, textAlign: 'right' }}>
                    {[{ label: 'rows', val: t.rows }, { label: 'cols', val: t.cols }, { label: 'size', val: t.size }].map(({ label, val }) => (
                      <div key={label}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: '#e8e9f0' }}>{val}</div>
                        <div style={{ fontSize: 10, color: '#5a5b72' }}>{label}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {/* Footer */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 20 }}>
              <span style={{ fontSize: 12, color: '#5a5b72' }}>
                {selectedCount > 0 ? `${selectedCount} table${selectedCount > 1 ? 's' : ''} selected` : 'No tables selected'}
              </span>
              <button
                onClick={handleContinue}
                disabled={selectedCount === 0}
                style={{
                  background: selectedCount === 0 ? '#2a2b3d' : '#6366f1',
                  color: selectedCount === 0 ? '#5a5b72' : '#fff',
                  border: 'none', padding: '10px 28px', borderRadius: 8,
                  fontSize: 14, fontWeight: 600,
                  cursor: selectedCount === 0 ? 'default' : 'pointer',
                  transition: 'all 0.15s',
                }}
              >
                Continue →
              </button>
            </div>
          </main>
        </div>
      </div>
    </div>
  )
}
