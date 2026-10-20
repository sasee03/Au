import { useState, useEffect, useRef } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import Sidebar from '../components/Sidebar'
import TopNav from '../components/TopNav'
import QualityDetailsModal from './QualityDetailsModal'

const API = 'http://localhost:4000/api'
const TABS = ['Connect','Select','Bronze Layer','Silver Layer','Gold Layer','Report']
const TAB_ROUTES = { Connect:'connect', Select:'select', 'Bronze Layer':'bronze', 'Silver Layer':'silver', 'Gold Layer':'gold', Report:'report' }

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

function StatIcon({ type }) {
  if (type === 'database') return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7"/></svg>
  if (type === 'tables') return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="16" rx="1"/><path d="M3 10h18M9 4v16"/></svg>
  if (type === 'warning') return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v5M12 18h.01"/></svg>
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round"><path d="M12 7v6M12 17h.01"/></svg>
}

function ScoreRing({ score }) {
  const color = score >= 90 ? '#22c55e' : score >= 70 ? '#f59e0b' : '#ef4444'
  const radius = 27
  const circumference = 2 * Math.PI * radius
  const progress = Math.max(0, Math.min(100, score)) / 100 * circumference
  return <div style={{ position:'relative', width:70, height:70, flexShrink:0 }}>
    <svg width="70" height="70" viewBox="0 0 70 70" style={{ transform:'rotate(-90deg)' }}>
      <circle cx="35" cy="35" r={radius} fill="none" stroke="#f1e6d9" strokeWidth="7" />
      <circle cx="35" cy="35" r={radius} fill="none" stroke={color} strokeWidth="7" strokeLinecap="round" strokeDasharray={`${progress} ${circumference}`} />
    </svg>
    <strong style={{ position:'absolute', inset:0, display:'flex', alignItems:'center', justifyContent:'center', color:'#633315', fontSize:12 }}>{score.toFixed(1)}%</strong>
  </div>
}

function QualityBadge({ status }) {
  const color = status === 'Pass' ? '#15803d' : status === 'Fail' ? '#b91c1c' : '#78716c'
  return <span style={{ display:'inline-block', color, background:`${color}14`, border:`1px solid ${color}40`, borderRadius:4, padding:'2px 6px', fontSize:10, fontWeight:700 }}>{status || 'N/A'}</span>
}

function TrendChart({ history, isPlaceholderData, loading }) {
  if (loading) return <div style={{ color:'#806f61', fontSize:12, padding:'24px 0' }}>Loading quality trend…</div>
  if (!history || history.length < 2) return <div style={{ color:'#806f61', fontSize:12, padding:'24px 0' }}>Not enough history yet. Run the DQ check again to build a trend.</div>
  const chartHistory = history.slice(-7)
  const width = 520
  const height = 135
  const min = Math.max(0, Math.floor(Math.min(...chartHistory.map(item => item.score)) / 10) * 10)
  const max = Math.min(100, Math.ceil(Math.max(...chartHistory.map(item => item.score)) / 10) * 10 || 100)
  const points = chartHistory.map((item, index) => `${index * (width / (chartHistory.length - 1))},${height - ((item.score - min) / Math.max(1, max - min)) * (height - 20)}`).join(' ')
  const formattedDates = chartHistory.map(item => new Date(item.timestamp).toLocaleDateString('en-GB', { day:'numeric', month:'short' }))
  const hasDuplicateDates = new Set(formattedDates).size !== formattedDates.length
  const dateLabels = hasDuplicateDates
    ? chartHistory.map((_, index) => {
      const date = new Date()
      date.setHours(12, 0, 0, 0)
      date.setDate(date.getDate() - (chartHistory.length - 1 - index))
      return date.toLocaleDateString('en-GB', { day:'numeric', month:'short' })
    })
    : formattedDates
  return <svg viewBox={`0 0 ${width} ${height + 28}`} width="100%" height="155" role="img" aria-label="DQ score history">
    {[0, 1, 2, 3].map(index => { const y = index * (height / 3); return <g key={index}><line x1="0" x2={width} y1={y} y2={y} stroke="#eadbca" /><text x="0" y={y + 12} fill="#806f61" fontSize="10">{Math.round(max - index * ((max - min) / 3))}%</text></g> })}
    <polyline points={points} fill="none" stroke="#f5822a" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
    {chartHistory.map((item, index) => {
      const x = index * (width / (chartHistory.length - 1))
      const y = height - ((item.score - min) / Math.max(1, max - min)) * (height - 20)
      return <g key={item.timestamp}>
        <circle cx={x} cy={y} r="4" fill="#f5822a" />
        <text x={x} y={height + 20} textAnchor="middle" fill="#806f61" fontSize="9">{dateLabels[index]}</text>
      </g>
    })}
  </svg>
}

function IssueDonut({ distribution }) {
  const total = distribution.reduce((sum, item) => sum + item.count, 0)
  const colors = { Critical:'#ef4444', High:'#f97316', Medium:'#f59e0b', Low:'#60a5fa' }
  let offset = 0
  const segments = distribution.map(item => {
    const value = total ? item.count / total * 100 : 0
    const segment = { ...item, value, offset }
    offset += value
    return segment
  })
  return <div style={{ display:'flex', alignItems:'center', gap:18 }}>
    <div style={{ position:'relative', width:112, height:112, flexShrink:0 }}>
      <svg viewBox="0 0 42 42" width="112" height="112" style={{ transform:'rotate(-90deg)' }}>
        <circle cx="21" cy="21" r="15.9" fill="none" stroke="#eee4d8" strokeWidth="7" />
        {total > 0 && segments.map(item => <circle key={item.level} cx="21" cy="21" r="15.9" fill="none" stroke={colors[item.level]} strokeWidth="7" strokeDasharray={`${item.value} ${100 - item.value}`} strokeDashoffset={-item.offset} />)}
      </svg>
      <div style={{ position:'absolute', inset:0, display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', color:'#633315' }}><strong style={{ fontSize:16 }}>{total}</strong><span style={{ fontSize:9 }}>Total Issues</span></div>
    </div>
    <div style={{ flex:1 }}>{segments.map(item => <div key={item.level} style={{ display:'grid', gridTemplateColumns:'72px 1fr 30px', gap:7, alignItems:'center', marginBottom:8, fontSize:10 }}><span style={{ color:'#633315' }}><i style={{ display:'inline-block', width:7, height:7, borderRadius:'50%', background:colors[item.level], marginRight:5 }} />{item.level}</span><div style={{ height:7, background:'#f1e6d9', borderRadius:5 }}><div style={{ width:`${item.value}%`, height:'100%', background:colors[item.level], borderRadius:5 }} /></div><span style={{ color:'#806f61', textAlign:'right' }}>{item.count} · {Math.round(item.value)}%</span></div>)}</div>
  </div>
}

export default function BronzeLayerPage() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()

  const [rows,        setRows]        = useState([])
  const [schema,      setSchema]      = useState([])
  const [loading,     setLoading]     = useState(true)
  const [activeTable, setActiveTable] = useState('')   // bare name, e.g. "olist_orders_dataset_bronze"
  const [qualityView, setQualityView] = useState(false)
  const [dictionaryView, setDictionaryView] = useState(false)
  const [dictionary, setDictionary] = useState([])
  const [dictionaryFilter, setDictionaryFilter] = useState('all')
  const [dictionaryLoading, setDictionaryLoading] = useState(false)
  const [dictionaryError, setDictionaryError] = useState('')
  const [dictionaryFallback, setDictionaryFallback] = useState(false)
  const [tableLabel,  setTableLabel]  = useState('')   // "bronze.olist_orders_dataset_bronze"
  const [selectedTables, setSelectedTables] = useState([]) // bare names filtered to session selection
  const [qualitySelectedTables, setQualitySelectedTables] = useState([])
  const [qualitySearch, setQualitySearch] = useState('')
  const [colCount,    setColCount]    = useState(0)
  const [rowCount,    setRowCount]    = useState('—')
  const [quality,     setQuality]     = useState(null)
  const [qualityDetailsOpen, setQualityDetailsOpen] = useState(false)
  const [qualityLoading, setQualityLoading] = useState(false)
  const [qualityError, setQualityError] = useState('')
  const [activeDqJob, setActiveDqJob] = useState(null)
  const [dqProgress, setDqProgress] = useState(null)
  const [progressChangedAt, setProgressChangedAt] = useState(Date.now())
  const previousProgressSignature = useRef('')

  const loadDictionary = async () => {
    const connection = sessionStorage.getItem('aurum_pg_conn')
    if (!connection) {
      setDictionaryError('Connect to PostgreSQL to view the source data dictionary.')
      setDictionaryView(true)
      return
    }
    setDictionaryLoading(true)
    setDictionaryError('')
    try {
      const response = await fetch(`${API}/bronze/dictionary`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pg_conn: JSON.parse(connection) }),
      })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || 'Data dictionary could not be loaded.')
      setDictionary(body.rows || [])
      setDictionaryFallback(Boolean(body.fallback_used))
      setDictionaryFilter('all')
      setDictionaryView(true)
    } catch (error) {
      setDictionaryError(error instanceof Error ? error.message : 'Data dictionary could not be loaded.')
      setDictionaryView(true)
    } finally {
      setDictionaryLoading(false)
    }
  }

  const getStoredQualityKey = () => `aurum_dq_report_v2:${sessionStorage.getItem('aurum_project_id') || 'unknown'}`
  const getStoredJobKey = tables => `aurum_dq_job_v1:${sessionStorage.getItem('aurum_project_id') || 'unknown'}:${encodeURIComponent([...tables].sort().join('|'))}`

  const readCachedQuality = () => {
    try {
      const raw = sessionStorage.getItem(getStoredQualityKey())
      if (!raw) return null
      const payload = JSON.parse(raw)
      if (payload && Array.isArray(payload.tables) && payload.report) return payload
    } catch {
      // Ignore invalid cached payloads.
    }
    return null
  }

  const writeCachedQuality = (report, tables) => {
    sessionStorage.setItem(getStoredQualityKey(), JSON.stringify({ report, tables, generated_at: new Date().toISOString() }))
  }

  const loadQuality = (tableNames, force = false) => {
    if (!tableNames || tableNames.length === 0) return
    const canonicalTables = [...new Set(tableNames)].sort()
    const jobKey = getStoredJobKey(canonicalTables)
    const storedJob = !force ? sessionStorage.getItem(jobKey) : null
    if (storedJob) {
      setActiveDqJob({ jobId: storedJob, tables: canonicalTables })
      setQualityLoading(true)
      return
    }
    const cached = readCachedQuality()
    if (!force && cached && JSON.stringify([...cached.tables].sort()) === JSON.stringify(canonicalTables)) {
      setQuality(cached.report)
      setQualityError('')
      return
    }
    setQualityLoading(true)
    setQualityError('')
    const pgConn = sessionStorage.getItem('aurum_pg_conn')
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 8000)
    fetch(`${API}/bronze/quality-report/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify({
        project_id: sessionStorage.getItem('aurum_project_id') || 'unknown',
        tables: canonicalTables,
        pg_conn: (sessionStorage.getItem('aurum_source') || 'csv') === 'postgres' && pgConn
          ? JSON.parse(pgConn)
          : null,
      }),
    })
      .then(async response => {
        const body = await response.text()
        if (!response.ok) {
          let detail = body
          try {
            detail = JSON.parse(body).detail || body
          } catch {
            // Keep the response text when the backend does not return JSON.
          }
          throw new Error(`Quality report job failed (${response.status}): ${detail}`)
        }
        return JSON.parse(body)
      })
      .then(body => {
        sessionStorage.setItem(getStoredJobKey(canonicalTables), body.job_id)
        setDqProgress(null)
        setActiveDqJob({ jobId: body.job_id, tables: canonicalTables })
      })
      .catch(error => {
        setQualityError(error.name === 'AbortError'
          ? 'The quality-report job request timed out. Please try again.'
          : error.message || 'Quality report could not be loaded.')
        setQualityLoading(false)
      })
      .finally(() => { clearTimeout(timeout); setQualityLoading(false) })
  }

  useEffect(() => {
    if (!activeDqJob?.jobId) return undefined
    let disposed = false
    let timer
    let controller
    const { jobId, tables } = activeDqJob
    const jobKey = getStoredJobKey(tables)

    const poll = async () => {
      controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 8000)
      try {
        const response = await fetch(
          `${API}/bronze/quality-report/jobs/${encodeURIComponent(jobId)}`,
          { signal: controller.signal },
        )
        const body = await response.json()
        if (!response.ok) throw new Error(body.detail || 'Quality report job could not be loaded.')
        if (disposed) return

        const progress = body.progress || {}
        const signature = JSON.stringify({
          phase: progress.phase,
          fast: progress.fast_tables_done,
          deep: progress.deep_tables_done,
          rows: progress.rows_done,
          current: progress.current_tables,
        })
        if (signature !== previousProgressSignature.current) {
          previousProgressSignature.current = signature
          setProgressChangedAt(Date.now())
        }
        setDqProgress(progress)
        setQualityLoading(body.status === 'queued' || body.status === 'running')
        if (body.status === 'queued' || body.status === 'running') {
          const partialTables = body.partial?.tables || []
          const checks = partialTables.flatMap(table => table.checks || [])
          const failedChecks = checks.filter(check => !check.passed)
          const score = partialTables.length
            ? partialTables.reduce((sum, table) => sum + (table.score || 0), 0) / partialTables.length
            : 0
          setQuality(previous => ({
            ...(previous || {}),
            dq_score: Number(score.toFixed(2)),
            passed_checks: partialTables.reduce((sum, table) => sum + (table.passed_checks || 0), 0),
            total_checks: partialTables.reduce((sum, table) => sum + (table.total_checks || 0), 0),
            issues_count: failedChecks
              .filter(check => ['Critical', 'High'].includes(check.severity))
              .reduce((sum, check) => sum + (check.bad_records || 0), 0),
            warnings_count: failedChecks
              .filter(check => ['Medium', 'Low'].includes(check.severity))
              .reduce((sum, check) => sum + (check.bad_records || 0), 0),
            rows_tested: progress.rows_done || 0,
            table_quality: partialTables,
            issues: failedChecks,
            check_results: checks,
            provisional: true,
          }))
        } else if (body.status === 'completed') {
          setQuality(body.report)
          writeCachedQuality(body.report, tables)
          sessionStorage.removeItem(jobKey)
          setActiveDqJob(null)
          setQualityLoading(false)
          return
        } else if (body.status === 'failed' || body.status === 'cancelled') {
          sessionStorage.removeItem(jobKey)
          setActiveDqJob(null)
          setQualityLoading(false)
          if (body.status === 'failed') {
            setQualityError(body.error || 'Quality report job failed.')
          } else {
            setQualityError('Quality report job was cancelled.')
          }
          return
        }
      } catch (error) {
        if (!disposed) {
          setQualityError(error.name === 'AbortError'
            ? 'Quality report status request timed out; polling will retry.'
            : error.message || 'Quality report status could not be loaded.')
        }
      } finally {
        clearTimeout(timeout)
        if (!disposed) timer = setTimeout(poll, 2000)
      }
    }

    setQualityLoading(true)
    poll()
    return () => {
      disposed = true
      clearTimeout(timer)
      controller?.abort()
    }
  }, [activeDqJob?.jobId])

  const loadPreview = (bareName) => {
    setLoading(true)
    setActiveTable(bareName)
    setQualityView(false)
    setDictionaryView(false)
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
        setQualitySelectedTables(sessionTables)

        // Determine which table to show first
        let target = null
        if (storedBronze) {
          const bare = storedBronze.replace('bronze.', '')
          if (sessionTables.includes(bare)) target = bare
        }
        if (!target) target = sessionTables[0]

        loadPreview(target)
        if (new URLSearchParams(location.search).get('view') === 'quality') {
          setQualityView(true)
          loadQuality(sessionTables)
        }
      })
      .catch(() => setLoading(false))
  }, [])

  const handleContinueToSilver = () => {
    navigate(`/project/${projectId}/silver`)
  }

  const goTab = t => navigate(`/project/${projectId}/${TAB_ROUTES[t]}`)
  const showQualityReport = () => {
    setDictionaryView(false)
    setQualityView(true)
    loadQuality(qualitySelectedTables)
  }
  const toggleQualityTable = table => setQualitySelectedTables(previous =>
    previous.includes(table) ? previous.filter(item => item !== table) : [...previous, table]
  )
  const toggleAllQualityTables = () => setQualitySelectedTables(
    qualitySelectedTables.length === selectedTables.length ? [] : selectedTables
  )
  const cols  = rows.length > 0 ? Object.keys(rows[0]).filter(k => !['dup','isNull'].includes(k)) : []
  const scoreColor = score => score >= 90 ? '#22c55e' : score >= 70 ? '#f59e0b' : '#ef4444'
  const severityColor = severity => ({ Critical:'#ef4444', High:'#f97316', Medium:'#f59e0b', Low:'#60a5fa' }[severity] || '#8b8ca8')
  const isPlaceholderData = quality?.is_placeholder_data
  const issueCount = quality?.issues_count
  const warningCount = quality?.warnings_count
  const tableCount = quality?.table_quality?.length
  const issueDistribution = ['Critical', 'High', 'Medium', 'Low'].map(level => ({
    level,
    count: quality?.issues?.filter(issue => issue.severity === level).reduce((sum, issue) => sum + issue.bad_records, 0) || 0,
  }))
  const severityRank = { Critical: 0, High: 1, Medium: 2, Low: 3 }
  const visibleQualityTables = selectedTables.filter(table => table.toLowerCase().includes(qualitySearch.toLowerCase()))
  const cachedQualityTables = readCachedQuality()?.tables || []
  const cachedQualitySelectionMismatch = quality && cachedQualityTables.length > 0 && JSON.stringify([...qualitySelectedTables].sort()) !== JSON.stringify([...cachedQualityTables].sort())
  const dictionaryTables = [...new Set(dictionary.map(row => row.table))].sort()
  const visibleDictionaryRows = dictionaryFilter === 'all'
    ? dictionary
    : dictionary.filter(row => row.table === dictionaryFilter)
  const isPostgresSource = (sessionStorage.getItem('aurum_source') || 'csv') === 'postgres'
  const fastTablesDone = dqProgress?.fast_tables_done || 0
  const deepTablesDone = dqProgress?.deep_tables_done || 0
  const totalProgressTables = dqProgress?.tables_total || activeDqJob?.tables?.length || 0
  const progressPercent = totalProgressTables
    ? Math.round(((fastTablesDone + deepTablesDone) / (2 * totalProgressTables)) * 100)
    : 0
  const durationLabel = seconds => {
    const value = Math.max(0, Math.floor(seconds || 0))
    return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`
  }
  const progressIsStalled = Boolean(activeDqJob && Date.now() - progressChangedAt >= 300000)

  const cancelDqJob = async () => {
    if (!activeDqJob?.jobId) return
    try {
      const response = await fetch(
        `${API}/bronze/quality-report/jobs/${encodeURIComponent(activeDqJob.jobId)}/cancel`,
        { method: 'POST', signal: AbortSignal.timeout(8000) },
      )
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || 'The quality-report job could not be cancelled.')
      setQualityError('Cancellation requested. Waiting for the running query to stop…')
    } catch (error) {
      setQualityError(error.message || 'The quality-report job could not be cancelled.')
    }
  }

  return (
    <div style={{ display:'flex', width:'100%', height:'100vh', background:'#0d0e14', overflow:'hidden' }}>
      <Sidebar onQuality={showQualityReport} qualityActive={qualityView} />
      <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>

        <TopNav
          tabs={TABS} activeTab="Bronze Layer" activeColor="#f59e0b"
          onTabChange={goTab}
          backLabel="Back to Datasets"
          onBack={() => navigate(`/project/${projectId}/select`)}
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
          {qualityView ? (
            <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between', marginBottom:18, padding:'2px 0 0', position:'relative' }}>
              <div style={{ display:'flex', alignItems:'flex-start', gap:12 }}>
                <div style={{ width:34, height:34, borderRadius:'50%', background:'#f5822a', color:'#fff', display:'flex', alignItems:'center', justifyContent:'center', fontSize:20, marginTop:2 }}>▤</div>
                <div>
                  <h2 style={{ fontSize:26, fontWeight:800, color:'#633315', marginBottom:3, letterSpacing:'0.01em' }}>DATA QUALITY DASHBOARD</h2>
                  <p style={{ color:'#806f61', fontSize:13 }}>Monitor data quality across tables, domains and pipelines</p>
                </div>
              </div>
              <span style={{ background:'#fff2df', color:'#d86518', border:'1px solid #f0c58d', fontSize:11, padding:'5px 10px', borderRadius:18, marginTop:6 }}>{selectedTables.length} tables</span>
            </div>
          ) : (
            <>
              <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:16, marginBottom:6, flexWrap:'wrap' }}>
                <div style={{ display:'flex', alignItems:'center', gap:10, flexWrap:'wrap' }}>
                  <h2 style={{ fontSize:22, fontWeight:700, color:'#e8e9f0' }}>Bronze Layer</h2>
                  {selectedTables.length > 1 && <span style={{ background:'rgba(245,158,11,0.1)', color:'#f59e0b', border:'1px solid rgba(245,158,11,0.3)', fontSize:11, padding:'3px 8px', borderRadius:20 }}>{selectedTables.length} tables</span>}
                </div>
                <div style={{ display:'flex', gap:7, alignItems:'center' }}>
                  <button onClick={showQualityReport} style={{ background:'#f5822a', color:'#fff', border:'none', borderRadius:6, padding:'8px 14px', fontSize:11, fontWeight:700, cursor:'pointer' }}>View Quality Report</button>
                  <button onClick={() => setDictionaryView(false)} style={{ background:dictionaryView ? '#1a1b25' : 'rgba(245,158,11,0.12)', color:dictionaryView ? '#8b8ca8' : '#f59e0b', border:`1px solid ${dictionaryView ? '#2a2b3d' : 'rgba(245,158,11,0.35)'}`, borderRadius:6, padding:'6px 10px', fontSize:11, cursor:'pointer' }}>Bronze data</button>
                  {isPostgresSource && <button onClick={loadDictionary} style={{ background:dictionaryView ? 'rgba(245,158,11,0.12)' : '#1a1b25', color:dictionaryView ? '#f59e0b' : '#8b8ca8', border:`1px solid ${dictionaryView ? 'rgba(245,158,11,0.35)' : '#2a2b3d'}`, borderRadius:6, padding:'6px 10px', fontSize:11, cursor:'pointer' }}>Data dictionary</button>}
                </div>
              </div>
              {!dictionaryView && <p style={{ color:'#8b8ca8', fontSize:13, marginBottom:18 }}>Raw data ingested exactly as-is from source. No modifications. Use the schema below when writing your Silver cleaning rules.</p>}
            </>
          )}

          {!qualityView && dictionaryView && <section style={{ background:'#1a1b25', border:'1px solid #2a2b3d', borderRadius:10, overflow:'hidden' }}>
            <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:12, padding:'12px 16px', borderBottom:'1px solid #2a2b3d', flexWrap:'wrap' }}>
              <div>
                <h3 style={{ color:'#e8e9f0', fontSize:14, marginBottom:4 }}>Data dictionary</h3>
                <span style={{ color:'#8b8ca8', fontSize:11 }}>{dictionary.length.toLocaleString()} columns</span>
              </div>
              <select value={dictionaryFilter} onChange={event => setDictionaryFilter(event.target.value)} style={{ background:'#0d0e14', color:'#e8e9f0', border:'1px solid #2a2b3d', borderRadius:6, padding:'7px 10px', fontSize:12 }}>
                <option value="all">All tables ({dictionaryTables.length})</option>
                {dictionaryTables.map(table => <option key={table} value={table}>{table}</option>)}
              </select>
            </div>
            {dictionaryFallback && <div style={{ padding:'9px 16px', background:'rgba(245,158,11,0.08)', color:'#fbbf24', fontSize:11, borderBottom:'1px solid #2a2b3d' }}>Dictionary table not found; displaying information_schema columns as a fallback.</div>}
            {dictionaryError && <div role="alert" style={{ padding:14, color:'#fca5a5', fontSize:12 }}>{dictionaryError}</div>}
            {dictionaryLoading ? <div style={{ padding:24, textAlign:'center', color:'#8b8ca8', fontSize:12 }}>Loading data dictionary…</div> : (
              <div style={{ overflowX:'auto', maxHeight:'65vh', overflowY:'auto' }}>
                <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
                  <thead style={{ position:'sticky', top:0, background:'#13141c' }}>
                    <tr>{['Table', 'Column #', 'Column', 'Data type', 'Source file', 'Status'].map(header => <th key={header} style={{ textAlign:'left', padding:'9px 12px', color:'#8b8ca8', fontSize:10, letterSpacing:'0.06em', whiteSpace:'nowrap' }}>{header}</th>)}</tr>
                  </thead>
                  <tbody>
                    {visibleDictionaryRows.map((item, index) => (
                      <tr key={`${item.table}-${item.column}-${index}`} style={{ borderTop:'1px solid #2a2b3d' }}>
                        <td style={{ padding:'8px 12px', color:'#e8e9f0', whiteSpace:'nowrap' }}>{item.table}</td>
                        <td style={{ padding:'8px 12px', color:'#8b8ca8' }}>{item.column_number}</td>
                        <td style={{ padding:'8px 12px', color:'#e8e9f0', whiteSpace:'nowrap' }}>{item.column}</td>
                        <td style={{ padding:'8px 12px', color:'#c4b5fd', whiteSpace:'nowrap' }}>{item.data_type}</td>
                        <td style={{ padding:'8px 12px', color:'#8b8ca8', whiteSpace:'nowrap' }}>{item.physical_files || '—'}</td>
                        <td style={{ padding:'8px 12px', whiteSpace:'nowrap' }}>
                          <span title={item.matches ? undefined : `Expected ${item.expected_type}; source has ${item.actual_type}`} style={{ display:'inline-block', color:item.matches ? '#86efac' : '#fca5a5', background:item.matches ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)', border:`1px solid ${item.matches ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`, borderRadius:4, padding:'2px 6px', fontSize:10, fontWeight:700 }}>{item.matches ? 'Match' : `Mismatch · ${item.actual_type}`}</span>
                        </td>
                      </tr>
                    ))}
                    {!dictionaryLoading && !dictionaryError && visibleDictionaryRows.length === 0 && <tr><td colSpan="6" style={{ padding:22, textAlign:'center', color:'#8b8ca8' }}>No dictionary columns found.</td></tr>}
                  </tbody>
                </table>
              </div>
            )}
          </section>}

          {/* Data Quality Dashboard */}
          {qualityView && <section style={{ marginBottom:24, color:'#1d2b36' }}>
            <div style={{ border:'1px solid #e6d7c7', borderRadius:7, background:'#fffdf9', padding:'12px 14px', marginBottom:14 }}>
              <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:10 }}>
                <strong style={{ color:'#633315', fontSize:13 }}>Select Tables</strong>
                <input value={qualitySearch} onChange={event => setQualitySearch(event.target.value)} placeholder="Search tables..." style={{ flex:1, border:'1px solid #e6d7c7', borderRadius:5, padding:'8px 10px', color:'#3b312a', background:'#fffaf3', fontSize:11, outline:'none' }} />
                <label style={{ display:'flex', alignItems:'center', gap:6, color:'#633315', fontSize:11, whiteSpace:'nowrap' }}><input type="checkbox" checked={selectedTables.length > 0 && qualitySelectedTables.length === selectedTables.length} onChange={toggleAllQualityTables} style={{ accentColor:'#f5822a' }} /> Select All</label>
                <span style={{ color:'#806f61', fontSize:11, whiteSpace:'nowrap' }}>{qualitySelectedTables.length} of {selectedTables.length} selected</span>
              </div>
              <div style={{ display:'grid', gridTemplateColumns:'repeat(2, minmax(0, 1fr))', gap:'7px 24px' }}>
                {visibleQualityTables.map(table => <label key={table} style={{ display:'flex', alignItems:'center', gap:7, color:'#3b312a', fontSize:11 }}><input type="checkbox" checked={qualitySelectedTables.includes(table)} onChange={() => toggleQualityTable(table)} style={{ accentColor:'#f5822a' }} /> {table.replace(/_bronze$/, '')}</label>)}
              </div>
              {cachedQualitySelectionMismatch && <div style={{ marginTop:8, color:'#a84f16', fontSize:11 }}>Selection changed - click Run DQ Check to update</div>}
            </div>
            <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between', gap:16, marginBottom:14, flexWrap:'wrap' }}>
              <div>
                <h3 style={{ fontSize:18, fontWeight:800, color:'#633315', marginBottom:4, textTransform:'uppercase', letterSpacing:'0.02em' }}>Overall Data Quality</h3>
                <p style={{ color:'#806f61', fontSize:12, margin:0 }}>Heuristic checks against the raw bronze data.</p>
              </div>
              <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                  <span style={{ color:'#806f61', fontSize:11 }}>
                  Last Run: {quality?.last_run ? new Date(quality.last_run).toLocaleString() : '—'}
                </span>
                <button onClick={() => loadQuality(qualitySelectedTables, true)} disabled={qualityLoading || qualitySelectedTables.length === 0} style={{
                  background: qualityLoading ? '#f0c5a3' : '#f5822a', color:'#fff', border:'none',
                  padding:'9px 18px', borderRadius:7, fontSize:12, fontWeight:800,
                  cursor: qualityLoading || selectedTables.length === 0 ? 'default' : 'pointer',
                }}>
                  {qualityLoading ? 'Checking…' : 'Run DQ Check'}
                </button>
              </div>
            </div>
            {qualityError && <div style={{ marginBottom:12, padding:'9px 12px', border:'1px solid #efb3a7', borderRadius:6, background:'#fff4f1', color:'#a33b2d', fontSize:11 }}>{qualityError}</div>}
            {activeDqJob && <div style={{ marginBottom:14, padding:'12px 14px', border:'1px solid #e6d7c7', borderRadius:7, background:'#fffdf9' }}>
              <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:12, marginBottom:8 }}>
                <strong style={{ color:'#633315', fontSize:12 }}>
                  {dqProgress?.phase_label || '1/2 fast'} - Fast checks {fastTablesDone}/{totalProgressTables} - Deep checks {deepTablesDone}/{totalProgressTables}
                  {' - '}{(dqProgress?.rows_done || 0).toLocaleString()} / {(dqProgress?.rows_total || 0).toLocaleString()} rows
                  {' - elapsed '}{durationLabel(dqProgress?.elapsed_s)}
                  {' - ETA '}{dqProgress?.eta_s == null ? '—' : durationLabel(dqProgress.eta_s)}
                </strong>
                <button onClick={cancelDqJob} style={{ border:'1px solid #d88c70', borderRadius:5, padding:'5px 12px', background:'#fff4f1', color:'#a33b2d', fontSize:11, fontWeight:700, cursor:'pointer' }}>Cancel</button>
              </div>
              <div role="progressbar" aria-valuenow={progressPercent} aria-valuemin="0" aria-valuemax="100" style={{ height:8, overflow:'hidden', borderRadius:5, background:'#f1e6d9' }}>
                <div style={{ width:`${progressPercent}%`, height:'100%', background:'#f5822a', transition:'width 250ms ease' }} />
              </div>
              {progressIsStalled && <div role="status" style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:10, marginTop:8, color:'#a33b2d', fontSize:11 }}>
                <span>Progress has not changed for 5 minutes; the job may be stalled.</span>
                <button onClick={cancelDqJob} style={{ border:'none', background:'transparent', color:'#a33b2d', fontWeight:700, textDecoration:'underline', cursor:'pointer' }}>Cancel job</button>
              </div>}
            </div>}

            <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(220px, 1fr))', gap:10, marginBottom:14 }}>
              {[
                ['DQ Score', quality?.dq_score ?? 0, quality ? scoreColor(quality.dq_score) : '#8b8ca8', 'score'],
                ['Issues', issueCount ?? '—', '#ef4444', 'alert'],
                ['Warnings', warningCount ?? '—', '#f59e0b', 'warning'],
                ['Rows Tested', quality?.rows_tested?.toLocaleString() ?? '—', '#60a5fa', 'database'],
                ['Tables', tableCount ?? '—', '#14b8a6', 'tables'],
              ].map(([label, value, color, icon]) => (
                <div key={label} style={{ background:'#fffdf9', border:'1px solid #e6d7c7', borderTop:`3px solid ${color}`, borderRadius:7, padding:'14px 16px' }}>
                  <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:7 }}>
                    {icon === 'score' ? <ScoreRing score={value} /> : <span style={{ width:30, height:30, borderRadius:'50%', background:color, display:'inline-flex', alignItems:'center', justifyContent:'center' }}><StatIcon type={icon} /></span>}
                    <div style={{ fontSize:10, color:'#806f61', textTransform:'uppercase', letterSpacing:'0.08em' }}>
                      {label}{icon === 'score' && (activeDqJob || quality?.provisional) && <span style={{ marginLeft:7, padding:'2px 5px', borderRadius:4, background:'#fff0dc', color:'#a84f16', fontSize:9 }}>Provisional</span>}
                    </div>
                  </div>
                  {icon === 'score' ? null : <div style={{ fontSize:25, fontWeight:800, color }}>{value}</div>}
                  {icon === 'score' && quality && <div style={{ fontSize:11, color:'#806f61', marginTop:4 }}>{quality.passed_checks} / {quality.total_checks} checks passed</div>}
                </div>
              ))}
            </div>

            <div style={{ background:'#fffdf9', border:'1px solid #e6d7c7', borderRadius:8, overflow:'hidden', marginBottom:14 }}>
              <div style={{ padding:'12px 14px', borderBottom:'1px solid #e6d7c7', display:'flex', alignItems:'center', justifyContent:'space-between', gap:12 }}>
                <span style={{ fontWeight:800, fontSize:13, color:'#633315', textTransform:'uppercase' }}>Issue-Wise Impact</span>
                {quality?.issues?.length > 0 && <button onClick={() => setQualityDetailsOpen(true)} style={{ background:'#fffaf3', border:'1px solid #f5822a', color:'#a84f16', borderRadius:4, padding:'5px 16px', fontSize:10, cursor:'pointer', whiteSpace:'nowrap' }}>View Details</button>}
              </div>
              {quality?.issues?.length ? (
                <div style={{ maxHeight:260, overflow:'auto' }}>
                  <table style={{ width:'100%', borderCollapse:'collapse', fontSize:11 }}>
                    <thead style={{ position:'sticky', top:0, background:'#f7eadb', zIndex:1 }}>
                      <tr>{['Severity','Table','Columns','Check','Impacted Records','No of Records','Issue %'].map(h => <th key={h} style={{ padding:'8px 10px', textAlign:'left', color:'#633315', fontWeight:700, whiteSpace:'nowrap' }}>{h}</th>)}</tr>
                    </thead>
                    <tbody>{[...quality.issues].sort((left, right) =>
                      (severityRank[left.severity] ?? 4) - (severityRank[right.severity] ?? 4)
                      || right.bad_pct - left.bad_pct
                    ).map((issue, index) => (
                      <tr key={`${issue.table_name}-${issue.column_name}-${issue.check_name || issue.rule}-${index}`} style={{ borderTop:'1px solid #eadbca' }}>
                        <td style={{ padding:'7px 10px', whiteSpace:'nowrap' }}><span style={{ background:`${severityColor(issue.severity)}22`, color:severityColor(issue.severity), border:`1px solid ${severityColor(issue.severity)}55`, borderRadius:4, padding:'2px 6px', fontSize:10 }}>{issue.severity}</span></td>
                        <td style={{ padding:'8px 10px', color:'#3b312a', whiteSpace:'nowrap' }}>{issue.table_name}</td>
                        <td style={{ padding:'8px 10px', color:'#806f61' }}>{issue.column_name === '__table__' ? 'Table-level' : issue.column_name}</td>
                        <td style={{ padding:'8px 10px', color:'#806f61' }}>{issue.check_name || issue.rule}</td>
                        <td style={{ padding:'8px 10px', color:'#3b312a', whiteSpace:'nowrap' }}>{issue.bad_records.toLocaleString()}</td>
                        <td style={{ padding:'8px 10px', color:'#3b312a', whiteSpace:'nowrap' }}>{issue.total_checked.toLocaleString()}</td>
                        <td style={{ padding:'8px 10px', minWidth:180 }}>
                          <div style={{ display:'flex', alignItems:'center', gap:9 }}>
                            <div style={{ flex:1, height:7, background:'#f1e6d9', borderRadius:5, overflow:'hidden' }}>
                              <div style={{ width:`${Math.min(100, Math.max(0, issue.bad_pct))}%`, height:'100%', background:'#f5822a', borderRadius:5 }} />
                            </div>
                            <span style={{ width:54, textAlign:'right', color:'#a84f16', fontWeight:700 }}>{issue.bad_pct.toFixed(2)}%</span>
                          </div>
                        </td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              ) : <div style={{ padding:16, color:'#22c55e', fontSize:12 }}>No issue percentages to display.</div>}
            </div>

            <div style={{ background:'#fffdf9', border:'1px solid #e6d7c7', borderRadius:8, overflow:'hidden', marginBottom:14 }}>
                <div style={{ padding:'12px 14px', borderBottom:'1px solid #e6d7c7', fontWeight:800, fontSize:13, color:'#633315', textTransform:'uppercase' }}>Quality by Table</div>
                {quality?.table_quality?.length ? (
                  <div style={{ overflowX:'auto' }}>
                    <table style={{ width:'100%', borderCollapse:'collapse', fontSize:11 }}>
                      <thead><tr style={{ background:'#f7eadb' }}>{['Table','Score','Passed Checks','Total Checks','Issues','Completeness','Uniqueness','Validity','Referential Integrity','Schema Integrity'].map(h => <th key={h} style={{ padding:'8px 10px', textAlign:'left', color:'#633315', fontWeight:700, whiteSpace:'nowrap' }}>{h}</th>)}</tr></thead>
                      <tbody>{quality.table_quality.map(table => <tr key={table.table_name} style={{ borderTop:'1px solid #eadbca' }}>
                        <td style={{ padding:'9px 10px', color:'#3b312a', whiteSpace:'nowrap' }}><span style={{ color:scoreColor(table.score), marginRight:6 }}>●</span>{table.table_name}</td>
                        <td style={{ padding:'8px 10px', color:scoreColor(table.score), fontWeight:600 }}>{table.score.toFixed(1)}%</td>
                        <td style={{ padding:'9px 10px', color:'#806f61' }}>{table.passed_checks}</td>
                        <td style={{ padding:'9px 10px', color:'#806f61' }}>{table.total_checks}</td>
                        <td style={{ padding:'9px 10px', color:'#3b312a' }}>{table.issue_count}</td>
                        {['Completeness','Uniqueness','Validity','Referential Integrity','Schema Integrity'].map(dimension => (
                          <td key={dimension} style={{ padding:'9px 10px' }}>
                            <QualityBadge status={table.dimension_status?.[dimension] || 'N/A'} />
                          </td>
                        ))}
                      </tr>)}</tbody>
                    </table>
                  </div>
                ) : <div style={{ padding:16, color:'#5a5b72', fontSize:12 }}>Run a check after bronze tables are available.</div>}
              </div>

            <div style={{ background:'#fffdf9', border:'1px solid #e6d7c7', borderRadius:8, overflow:'hidden', marginTop:14 }}>
              <div style={{ padding:'12px 14px', borderBottom:'1px solid #e6d7c7', fontWeight:800, fontSize:13, color:'#633315', textTransform:'uppercase' }}>Referential Integrity</div>
              {quality?.referential_integrity?.length ? (
                <div style={{ overflowX:'auto' }}>
                  <table style={{ width:'100%', borderCollapse:'collapse', fontSize:11 }}>
                    <thead><tr style={{ background:'#f7eadb' }}>{['Child Table','FK Column','Parent Table','PK Column','Rows Checked','FK Failures','RI %','Status'].map(h => <th key={h} style={{ padding:'8px 10px', textAlign:'left', color:'#633315', fontWeight:700, whiteSpace:'nowrap' }}>{h}</th>)}</tr></thead>
                    <tbody>{quality.referential_integrity.map((relationship, index) => <tr key={`${relationship.child_table}-${relationship.fk_column}-${index}`} style={{ borderTop:'1px solid #eadbca' }}>
                      <td style={{ padding:'9px 10px', color:'#3b312a', whiteSpace:'nowrap' }}>{relationship.child_table}</td>
                      <td style={{ padding:'9px 10px', color:'#806f61' }}>{relationship.fk_column}</td>
                      <td style={{ padding:'9px 10px', color:'#3b312a', whiteSpace:'nowrap' }}>{relationship.parent_table}</td>
                      <td style={{ padding:'9px 10px', color:'#806f61' }}>{relationship.pk_column}</td>
                      <td style={{ padding:'9px 10px', color:'#3b312a' }}>{relationship.rows_checked.toLocaleString()}</td>
                      <td style={{ padding:'9px 10px', color:relationship.fk_failures ? '#b91c1c' : '#3b312a' }}>{relationship.fk_failures.toLocaleString()}</td>
                      <td style={{ padding:'9px 10px', color:'#3b312a' }}>{relationship.ri_pct.toFixed(2)}%</td>
                      <td style={{ padding:'9px 10px' }}><QualityBadge status={relationship.status} /></td>
                    </tr>)}</tbody>
                  </table>
                </div>
              ) : <div style={{ padding:16, color:'#5a5b72', fontSize:12 }}>No declared foreign key relationships found in the source database.</div>}
            </div>

            <div style={{ display:'grid', gridTemplateColumns:'minmax(0, 1.2fr) minmax(260px, 0.8fr)', gap:14, marginTop:14 }}>
              <div style={{ background:'#fffdf9', border:'1px solid #e6d7c7', borderRadius:8, padding:'12px 14px' }}>
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:12, gap:10 }}>
                  <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                    <span style={{ fontWeight:800, fontSize:13, color:'#633315', textTransform:'uppercase' }}>Quality Trends</span>
                    {isPlaceholderData && <span style={{ color:'#806f61', fontSize:10, fontStyle:'italic' }}>Demo data — showing sample trend until more runs are recorded</span>}
                  </div>
                  <span style={{ color:'#d86518', fontSize:11, whiteSpace:'nowrap' }}>● Current DQ score</span>
                </div>
                <TrendChart history={quality?.history} isPlaceholderData={quality?.is_placeholder_data} loading={qualityLoading && !quality} />
              </div>

              <div style={{ background:'#fffdf9', border:'1px solid #e6d7c7', borderRadius:8, padding:'12px 14px' }}>
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:12 }}>
                  <span style={{ fontWeight:800, fontSize:13, color:'#633315', textTransform:'uppercase' }}>Issue Distribution</span>
                  <span style={{ fontSize:11, color:'#806f61' }}>{quality?.issues?.length || 0} rules</span>
                </div>
                <IssueDonut distribution={issueDistribution} />
              </div>
            </div>
          </section>}

          {/* Active table preview */}
          {!qualityView && !dictionaryView && <>
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
          </>}
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
      {qualityDetailsOpen && <QualityDetailsModal issues={quality?.issues || []} onClose={() => setQualityDetailsOpen(false)} />}
    </div>
  )
}
