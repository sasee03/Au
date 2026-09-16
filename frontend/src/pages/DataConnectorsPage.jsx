import { useState, useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Sidebar from '../components/Sidebar'
import TopNav from '../components/TopNav'

const API = 'http://localhost:4000/api'
const TABS = ['Connect','Select','Configure Pipeline','Bronze Layer','Silver Layer','Gold Layer','Report']
const TAB_ROUTES = { Connect:'connect', Select:'select', 'Configure Pipeline':'pipeline-config', 'Bronze Layer':'bronze', 'Silver Layer':'silver', 'Gold Layer':'gold', Report:'report' }

const connectors = [
  { id: 'csv',      label: 'Local CSV',   abbr: 'Cs' },
  { id: 'postgres', label: 'PostgreSQL',  abbr: 'Pg' },
]

const iconUpload = (
  <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#5a5b72" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/>
    <path d="M20.39 18.39A5 5 0 0018 9h-1.26A8 8 0 103 16.3"/>
  </svg>
)
const iconSearch = (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
  </svg>
)
const iconChevDown = (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <polyline points="6 9 12 15 18 9"/>
  </svg>
)

export default function DataConnectorsPage() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const fileRef  = useRef(null)

  const [selected,      setSelected]    = useState('csv')
  const [datasetName,   setDatasetName] = useState('')
  const [csvFile,       setCsvFile]     = useState(null)
  const [delimiter,     setDelimiter]   = useState('Comma (,)')
  const [encoding,      setEncoding]    = useState('UTF-8')
  const [firstRow,      setFirstRow]    = useState(true)
  const [dragOver,      setDragOver]    = useState(false)
  const [uploading,     setUploading]   = useState(false)

  // Postgres
  const [host,          setHost]       = useState('localhost')
  const [port,          setPort]       = useState('5432')
  const [database,      setDatabase]   = useState('')
  const [schema,        setSchema]     = useState('public')
  const [username,      setUsername]   = useState('postgres')
  const [password,      setPassword]   = useState('')
  const [showPass,      setShowPass]   = useState(false)
  const [ssl,           setSsl]        = useState(false)
  const [testing,       setTesting]    = useState(false)
  const [testMsg,       setTestMsg]    = useState('')

  const inputStyle = {
    width: '100%', background: '#0d0e14', border: '1px solid #2a2b3d',
    borderRadius: 7, padding: '8px 11px', color: '#e8e9f0', fontSize: 13,
    outline: 'none', transition: 'border-color 0.15s'
  }
  const labelStyle = {
    fontSize: 10.5, fontWeight: 600, letterSpacing: '0.1em',
    color: '#8b8ca8', textTransform: 'uppercase', display: 'block', marginBottom: 6
  }
  const onFocus = e => e.target.style.borderColor = '#6366f1'
  const onBlur  = e => e.target.style.borderColor = '#2a2b3d'

  // ── CSV: upload file then go to pipeline-config ──────────────────
  const handleFileChange = e => {
    const f = e.target.files?.[0]
    if (f) { setCsvFile(f); setDatasetName(prev => prev || f.name.replace('.csv', '')) }
  }
  const handleDrop = e => {
    e.preventDefault(); setDragOver(false)
    const f = e.dataTransfer.files?.[0]
    if (f) { setCsvFile(f); setDatasetName(prev => prev || f.name.replace('.csv', '')) }
  }

  const handleConfigurePipeline = async () => {
    if (selected === 'csv') {
      sessionStorage.setItem('aurum_source', 'csv')
      sessionStorage.setItem('aurum_dataset', datasetName || 'dataset')
      // Clear any stale table/schema data from a previous session
      sessionStorage.removeItem('aurum_selected_tables')
      sessionStorage.removeItem('aurum_bronze_table')
      sessionStorage.removeItem('aurum_bronze_schema')
      sessionStorage.removeItem('aurum_silver_result')
      sessionStorage.removeItem('aurum_silver_results')
      if (csvFile) {
        setUploading(true)
        try {
          const fd = new FormData()
          fd.append('file', csvFile)
          fd.append('dataset_name', datasetName || csvFile.name.replace('.csv',''))
          fd.append('delimiter', delimiter)
          fd.append('encoding', encoding)
          fd.append('first_row_header', firstRow)
          fd.append('project_id', sessionStorage.getItem('aurum_project_id') || '')
          const res = await fetch(`${API}/bronze/upload`, { method: 'POST', body: fd }).catch(() => null)
          if (res?.ok) {
            const d = await res.json()
            // Store bronze table name and base_name for downstream pages
            if (d.bronze_table) sessionStorage.setItem('aurum_bronze_table', d.bronze_table)
            if (d.base_name)    sessionStorage.setItem('aurum_base_name',    d.base_name)
            sessionStorage.setItem('aurum_schema_info', JSON.stringify(d.schema_cols || []))
          }
        } finally { setUploading(false) }
      }
      // CSV → pipeline-config (no table selection needed)
      navigate(`/project/${projectId}/pipeline-config`)
    } else {
      // Postgres → store full conn including password, then go to /select to pick tables
      // Clear stale table/schema data from any previous session
      sessionStorage.removeItem('aurum_selected_tables')
      sessionStorage.removeItem('aurum_bronze_table')
      sessionStorage.removeItem('aurum_bronze_schema')
      sessionStorage.removeItem('aurum_silver_result')
      sessionStorage.removeItem('aurum_silver_results')
      sessionStorage.setItem('aurum_source', 'postgres')
      sessionStorage.setItem('aurum_pg_conn', JSON.stringify({
        host, port, database, schema, username, password, ssl
      }))

      // Derive base_name from project name for postgres (no single CSV filename to use).
      // e.g. "Olist Retail" → "olist_retail", "My Project" → "my_project"
      const projectName = sessionStorage.getItem('aurum_project_name') || database || 'project'
      const baseName = projectName
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '_')
        .replace(/^_+|_+$/g, '') || 'project'
      sessionStorage.setItem('aurum_base_name', baseName)

      navigate(`/project/${projectId}/select`)
    }
  }

  // ── PostgreSQL: test connection ───────────────────────────────────
  const handleTestConnection = async () => {
    setTesting(true); setTestMsg('')
    try {
      const res = await fetch(`${API}/postgres/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host, port: Number(port), database, schema, username, password, ssl })
      })
      const d = await res.json()
      setTestMsg(d.ok ? '✓ Connection successful' : `✗ ${d.error}`)
    } catch {
      setTestMsg('Backend not reachable — fill details and continue anyway.')
    } finally { setTesting(false) }
  }

  return (
    <div style={{ display: 'flex', width: '100%', height: '100vh', background: '#0d0e14', overflow: 'hidden' }}>
      <Sidebar />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        <TopNav
          tabs={TABS} activeTab="Connect" activeColor="#6366f1"
          onTabChange={t => navigate(`/project/${projectId}/${TAB_ROUTES[t]}`)}
        />

        {/* Body */}
        <div style={{ flex: 1, display: 'flex', padding: '28px 28px', gap: 28, overflow: 'auto', alignItems: 'flex-start' }}>
          {/* Left */}
          <div style={{ flexShrink: 0 }}>
            <h2 style={{ fontSize: 20, fontWeight: 700, color: '#e8e9f0', marginBottom: 5 }}>Connect Data Sources</h2>
            <p style={{ color: '#8b8ca8', fontSize: 13, marginBottom: 22 }}>Select a system to configure your connection.</p>
            <div style={{ display: 'flex', gap: 10 }}>
              {connectors.map(c => (
                <button key={c.id} onClick={() => setSelected(c.id)} style={{
                  width: 112, padding: '18px 10px 14px', borderRadius: 10, cursor: 'pointer',
                  background: selected === c.id ? 'rgba(99,102,241,0.1)' : '#13141c',
                  border: selected === c.id ? '1.5px solid #6366f1' : '1px solid #2a2b3d',
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, transition: 'all 0.15s'
                }}>
                  <div style={{ width: 46, height: 46, borderRadius: 12, background: selected === c.id ? 'rgba(99,102,241,0.25)' : 'rgba(99,102,241,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, fontWeight: 700, color: '#818cf8' }}>{c.abbr}</div>
                  <span style={{ fontSize: 12, color: selected === c.id ? '#e8e9f0' : '#8b8ca8', fontWeight: 500 }}>{c.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Right panel */}
          <div style={{ flex: 1, background: '#13141c', border: '1px solid #2a2b3d', borderRadius: 12, padding: '22px 24px', minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 22 }}>
              <div style={{ width: 34, height: 34, borderRadius: 8, background: 'rgba(99,102,241,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700, color: '#818cf8' }}>{selected === 'csv' ? 'Cs' : 'Pg'}</div>
              <span style={{ fontSize: 15, fontWeight: 600, color: '#e8e9f0' }}>{selected === 'csv' ? 'Local CSV' : 'PostgreSQL'}</span>
            </div>

            {selected === 'csv' ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
                <div>
                  <label style={labelStyle}>Dataset Name</label>
                  <input placeholder="e.g. orders_2024" value={datasetName}
                    onChange={e => setDatasetName(e.target.value)}
                    style={inputStyle} onFocus={onFocus} onBlur={onBlur} />
                </div>
                <div>
                  <label style={labelStyle}>Upload CSV</label>
                  <input ref={fileRef} type="file" accept=".csv" style={{ display: 'none' }} onChange={handleFileChange} />
                  <div
                    onDragOver={e => { e.preventDefault(); setDragOver(true) }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={handleDrop}
                    onClick={() => fileRef.current?.click()}
                    style={{
                      border: `2px dashed ${dragOver ? '#6366f1' : csvFile ? '#22c55e' : '#2a2b3d'}`,
                      borderRadius: 8, padding: '36px 20px', textAlign: 'center',
                      background: dragOver ? 'rgba(99,102,241,0.05)' : '#0d0e14',
                      cursor: 'pointer', transition: 'all 0.15s'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 12 }}>{iconUpload}</div>
                    {csvFile
                      ? <div style={{ fontSize: 13, color: '#22c55e', fontWeight: 500 }}>✓ {csvFile.name}</div>
                      : <div style={{ fontSize: 13, color: '#8b8ca8' }}><span style={{ color: '#6366f1', fontWeight: 500 }}>Click to upload</span> or drag and drop</div>
                    }
                    <div style={{ fontSize: 12, color: '#5a5b72', marginTop: 4 }}>CSV files only</div>
                  </div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                  <div>
                    <label style={labelStyle}>Delimiter</label>
                    <div style={{ position: 'relative' }}>
                      <select value={delimiter} onChange={e => setDelimiter(e.target.value)} style={{ ...inputStyle, appearance: 'none', paddingRight: 30 }}>
                        {['Comma (,)', 'Tab (\\t)', 'Semicolon (;)', 'Pipe (|)'].map(o => <option key={o}>{o}</option>)}
                      </select>
                      <span style={{ position: 'absolute', right: 9, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none', color: '#8b8ca8' }}>{iconChevDown}</span>
                    </div>
                  </div>
                  <div>
                    <label style={labelStyle}>Encoding</label>
                    <div style={{ position: 'relative' }}>
                      <select value={encoding} onChange={e => setEncoding(e.target.value)} style={{ ...inputStyle, appearance: 'none', paddingRight: 30 }}>
                        {['UTF-8', 'UTF-16', 'ASCII', 'ISO-8859-1'].map(o => <option key={o}>{o}</option>)}
                      </select>
                      <span style={{ position: 'absolute', right: 9, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none', color: '#8b8ca8' }}>{iconChevDown}</span>
                    </div>
                  </div>
                </div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13, color: '#e8e9f0' }}>
                  <input type="checkbox" checked={firstRow} onChange={e => setFirstRow(e.target.checked)} style={{ width: 15, height: 15, accentColor: '#6366f1' }} />
                  First row is header
                </label>
                <div style={{ display: 'flex', gap: 10 }}>
                  <button style={{ background: '#1a1b25', color: '#e8e9f0', border: '1px solid #2a2b3d', padding: '8px 16px', borderRadius: 7, fontSize: 13, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
                    {iconSearch} Preview File
                  </button>
                  <button onClick={handleConfigurePipeline} disabled={uploading} style={{
                    background: uploading ? '#4a4c8a' : '#6366f1', color: '#fff', border: 'none',
                    padding: '8px 18px', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: uploading ? 'default' : 'pointer'
                  }}>{uploading ? 'Uploading…' : 'Configure Pipeline →'}</button>                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 90px', gap: 12 }}>
                  <div><label style={labelStyle}>Host</label><input placeholder="localhost" value={host} onChange={e => setHost(e.target.value)} style={inputStyle} onFocus={onFocus} onBlur={onBlur} /></div>
                  <div><label style={labelStyle}>Port</label><input placeholder="5432" value={port} onChange={e => setPort(e.target.value)} style={inputStyle} onFocus={onFocus} onBlur={onBlur} /></div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div><label style={labelStyle}>Database</label><input placeholder="my_database" value={database} onChange={e => setDatabase(e.target.value)} style={inputStyle} onFocus={onFocus} onBlur={onBlur} /></div>
                  <div><label style={labelStyle}>Schema</label><input placeholder="public" value={schema} onChange={e => setSchema(e.target.value)} style={inputStyle} onFocus={onFocus} onBlur={onBlur} /></div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div><label style={labelStyle}>Username</label><input placeholder="postgres" value={username} onChange={e => setUsername(e.target.value)} style={inputStyle} onFocus={onFocus} onBlur={onBlur} /></div>
                  <div>
                    <label style={labelStyle}>Password</label>
                    <div style={{ position: 'relative' }}>
                      <input type={showPass ? 'text' : 'password'} placeholder="••••••••" value={password} onChange={e => setPassword(e.target.value)} style={{ ...inputStyle, paddingRight: 46 }} onFocus={onFocus} onBlur={onBlur} />
                      <button onClick={() => setShowPass(p => !p)} style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: '#8b8ca8', cursor: 'pointer', fontSize: 11.5 }}>{showPass ? 'Hide' : 'Show'}</button>
                    </div>
                  </div>
                </div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13, color: '#e8e9f0' }}>
                  <input type="checkbox" checked={ssl} onChange={e => setSsl(e.target.checked)} style={{ width: 15, height: 15, accentColor: '#6366f1' }} />
                  Enable SSL
                </label>
                {testMsg && <p style={{ fontSize: 12, color: testMsg.startsWith('✓') ? '#22c55e' : '#f59e0b', background: '#0d0e14', padding: '8px 12px', borderRadius: 6, margin: 0 }}>{testMsg}</p>}
                <div style={{ display: 'flex', gap: 10 }}>
                  <button onClick={handleTestConnection} disabled={testing} style={{
                    background: '#1a1b25', color: '#e8e9f0', border: '1px solid #2a2b3d',
                    padding: '8px 16px', borderRadius: 7, fontSize: 13, cursor: 'pointer', fontWeight: 500
                  }}>{testing ? 'Testing…' : 'Test Connection'}</button>
                  <button onClick={handleConfigurePipeline} style={{
                    background: '#6366f1', color: '#fff', border: 'none',
                    padding: '8px 18px', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer'
                  }}>Select Tables →</button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
