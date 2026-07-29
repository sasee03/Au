import React from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Sidebar from '../components/Sidebar'
import TopNav from '../components/TopNav'

const TABS = ['Connect','Select','Configure Pipeline','Bronze Layer','Silver Layer','Gold Layer','Report']
const TAB_ROUTES = { Connect:'connect', Select:'select', 'Configure Pipeline':'pipeline-config', 'Bronze Layer':'bronze', 'Silver Layer':'silver', 'Gold Layer':'gold', Report:'report' }

const bronzePoints = [
  'Exact raw copy of source data — no transformations applied',
  'Schema inferred automatically from the uploaded file or source database',
  'Column types detected from actual data values',
  'Bad data intentionally preserved — NULLs, duplicates, outliers all kept',
  'Provides the schema context passed to the AI for Silver SQL generation',
]
const silverPoints = [
  'You describe cleaning rules in plain English or add them manually',
  'AI reads information_schema and generates transformation SQL per rule',
  'Each rule gets its own SQL — independently reviewable',
  'Safety checks run before executions no DROP/DELETE allowed',
  'You Approve & Execute — nothing runs without your confirmation',
]
const goldPoints = [
  'You describe your business requirement in plain language',
  'AI identifies your domain and KPIs automatically',
  'SQL generated for each KPI — SUM, COUNT, AVG, GROUP BY',
  'Gold data preview shown before execution',
  'Gold tables feed dashboards, BI tools, and ML models',
]

const executionSteps = [
  { step: 'STEP 1 · AUTO', label: 'Ingest to Bronze', who: 'Auto', desc: 'Run copy to bronze_database, metadata added. ~5 sec.' },
  { step: 'STEP 2 · YOU DEFINE', label: 'Write Cleaning Rules', who: 'You', desc: 'Add rules manually or describe in plain English.' },
  { step: 'STEP 3 · AI', label: 'Generate Silver SQL', who: 'AI', desc: 'AI reads schema, writes any SQL per rule.' },
  { step: 'STEP 4 · YOU APPROVE', label: 'Review & Execute Silver', who: 'You', desc: 'Safety checks pass — you click Approve & Execute.' },
  { step: 'STEP 5 · YOU DEFINE', label: 'Define Gold KPIs', who: 'You', desc: 'Describe business goal — AI generates KPI SQL.' },
  { step: 'STEP 6 · DONE', label: 'Gold & Dashboard', who: 'Done', desc: 'Gold tables ready. View results and export.' },
]

const stepColor = { 'Auto': '#22c55e', 'You': '#6366f1', 'AI': '#818cf8', 'Done': '#f59e0b' }

export default function PipelineConfigPage() {
  const navigate = useNavigate()
  const { projectId } = useParams()
  const [ingesting, setIngesting] = React.useState(false)

  const handleStartPipeline = async () => {
    const source  = sessionStorage.getItem('aurum_source') || 'csv'
    const tables  = JSON.parse(sessionStorage.getItem('aurum_selected_tables') || '[]')
    const pgConn  = (() => { try { return JSON.parse(sessionStorage.getItem('aurum_pg_conn') || 'null') } catch { return null } })()

    // For CSV the file was already uploaded on Connect page — just navigate
    if (source !== 'postgres' || tables.length === 0) {
      navigate(`/project/${projectId}/bronze`)
      return
    }

    // For postgres: trigger ingest now so Bronze page has data on arrival
    setIngesting(true)
    try {
      await fetch(`http://localhost:4000/api/bronze/ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: sessionStorage.getItem('aurum_project_id') || null,
          tables,
          source: 'postgres',
          pg_conn: pgConn,
        }),
      })
    } catch {
      // If ingest fails, still navigate — Bronze page will show empty state
    } finally {
      setIngesting(false)
      navigate(`/project/${projectId}/bronze`)
    }
  }

  return (
    <div style={{ display: 'flex', width: '100%', height: '100vh', background: '#0d0e14', overflow: 'hidden' }}>
      <Sidebar />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <TopNav
          tabs={TABS} activeTab="Configure Pipeline" activeColor="#6366f1"
          onTabChange={t => navigate(`/project/${projectId}/${TAB_ROUTES[t]}`)}
          backLabel="Back to Datasets"
          onBack={() => navigate(`/project/${projectId}/select`)}
        />

        <main style={{ flex: 1, padding: '24px 28px', overflow: 'auto' }}>
          <h2 style={{ fontSize: 22, fontWeight: 700, color: '#e8e9f0', marginBottom: 4 }}>Pipeline Configuration</h2>
          <p style={{ color: '#8b8ca8', fontSize: 13, marginBottom: 28 }}>
            Review what happens at each medallion layer before starting the pipeline. Nothing is executed until you click Start.
          </p>

          {/* Section 1 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
            <div style={{ width: 28, height: 28, borderRadius: '50%', background: '#1e1f2e', border: '1px solid #2a2b3d', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700, color: '#e8e9f0' }}>1</div>
            <span style={{ fontWeight: 600, fontSize: 15, color: '#e8e9f0' }}>Medallion Pipeline Stages</span>
            <span style={{ fontSize: 12, color: '#8b8ca8' }}>What will happen at each layer</span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr auto 1fr', gap: 0, marginBottom: 32, alignItems: 'stretch' }}>
            {/* Bronze */}
            <div style={{ background: '#1a1b25', border: '1px solid #2a2b3d', borderTop: '2px solid #f59e0b', borderRadius: 10, padding: '20px' }}>
              <div style={{ fontWeight: 700, fontSize: 15, color: '#e8e9f0', marginBottom: 2 }}>Bronze Layer</div>
              <div style={{ fontSize: 11, color: '#5a5b72', marginBottom: 14 }}>— bronze schema</div>
              {bronzePoints.map((p, i) => (
                <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8, fontSize: 12.5, color: '#8b8ca8', lineHeight: 1.5 }}>
                  <span style={{ color: '#5a5b72', flexShrink: 0, marginTop: 2 }}>●</span>
                  <span dangerouslySetInnerHTML={{ __html: p.replace(/([a-z_]+)/g, (m) => ['ingested_at','source_file','information_schema','NULLs'].includes(m) ? `<strong style="color:#e8e9f0">${m}</strong>` : m) }} />
                </div>
              ))}
              <div style={{ marginTop: 14, background: '#13141c', borderRadius: 6, padding: '8px 12px', fontSize: 11, color: '#5a5b72', display: 'flex', alignItems: 'center', gap: 6 }}>
                ~3 seconds · Automatic
              </div>
            </div>

            {/* Arrow */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 8px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                <div style={{ fontSize: 10, color: '#5a5b72', fontWeight: 600 }}>FLOW</div>
                <div style={{ color: '#6366f1', fontSize: 18 }}>→</div>
              </div>
            </div>

            {/* Silver */}
            <div style={{ background: '#1a1b25', border: '1px solid #6366f1', borderTop: '2px solid #6366f1', borderRadius: 10, padding: '20px' }}>
              <div style={{ fontWeight: 700, fontSize: 15, color: '#e8e9f0', marginBottom: 2 }}>Silver Layer</div>
              <div style={{ fontSize: 11, color: '#5a5b72', marginBottom: 14 }}>— silver schema</div>
              {silverPoints.map((p, i) => (
                <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8, fontSize: 12.5, color: '#8b8ca8', lineHeight: 1.5 }}>
                  <span style={{ color: '#5a5b72', flexShrink: 0, marginTop: 2 }}>●</span>
                  <span>{p}</span>
                </div>
              ))}
              <div style={{ marginTop: 14, background: '#13141c', borderRadius: 6, padding: '8px 12px', fontSize: 11, color: '#5a5b72', display: 'flex', alignItems: 'center', gap: 6 }}>
                Your rules · AI writes SQL · You execute
              </div>
            </div>

            {/* Arrow */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 8px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                <div style={{ fontSize: 10, color: '#5a5b72', fontWeight: 600 }}>FLOW</div>
                <div style={{ color: '#6366f1', fontSize: 18 }}>→</div>
              </div>
            </div>

            {/* Gold */}
            <div style={{ background: '#1a1b25', border: '1px solid #2a2b3d', borderTop: '2px solid #f59e0b', borderRadius: 10, padding: '20px' }}>
              <div style={{ fontWeight: 700, fontSize: 15, color: '#e8e9f0', marginBottom: 2 }}>Gold Layer</div>
              <div style={{ fontSize: 11, color: '#5a5b72', marginBottom: 14 }}>— gold schema</div>
              {goldPoints.map((p, i) => (
                <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8, fontSize: 12.5, color: '#8b8ca8', lineHeight: 1.5 }}>
                  <span style={{ color: '#5a5b72', flexShrink: 0, marginTop: 2 }}>●</span>
                  <span>{p}</span>
                </div>
              ))}
              <div style={{ marginTop: 14, background: '#13141c', borderRadius: 6, padding: '8px 12px', fontSize: 11, color: '#5a5b72', display: 'flex', alignItems: 'center', gap: 6 }}>
                Business KPIs · AI SQL · Dashboard ready
              </div>
            </div>
          </div>

          {/* Section 2: Execution Timeline */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
            <div style={{ width: 28, height: 28, borderRadius: '50%', background: '#1e1f2e', border: '1px solid #2a2b3d', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700, color: '#e8e9f0' }}>2</div>
            <span style={{ fontWeight: 600, fontSize: 15, color: '#e8e9f0' }}>Execution Timeline</span>
            <span style={{ fontSize: 12, color: '#8b8ca8' }}>Step-by-step order</span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 10, marginBottom: 28 }}>
            {executionSteps.map((s, i) => (
              <div key={i} style={{ background: '#1a1b25', border: '1px solid #2a2b3d', borderRadius: 10, padding: '14px 12px' }}>
                <div style={{ fontSize: 10, color: '#5a5b72', marginBottom: 6, fontWeight: 600 }}>{s.step}</div>
                <div style={{ fontSize: 12.5, fontWeight: 600, color: '#e8e9f0', marginBottom: 6 }}>{s.label}</div>
                <div style={{ fontSize: 11, color: '#8b8ca8', lineHeight: 1.5 }}>{s.desc}</div>
              </div>
            ))}
          </div>

          {/* Info */}
          <div style={{ background: '#1a1b25', border: '1px solid #2a2b3d', borderRadius: 10, padding: '14px 18px', display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}>
            <span style={{ color: '#6366f1', fontSize: 16 }}>ℹ</span>
            <span style={{ fontSize: 13, color: '#8b8ca8' }}>
              <strong style={{ color: '#e8e9f0' }}>Nothing is executed automatically.</strong> Each layer requires your explicit approval before data is written. You can stop at any stage.
            </span>
          </div>
        </main>

        {/* Footer bar */}
        <div style={{
          height: 52, background: '#0f1018', borderTop: '1px solid #1e1f2e',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingInline: 24
        }}>
          <button onClick={() => navigate(`/project/${projectId}/select`)} style={{
            background: '#1e1f2e', color: '#e8e9f0', border: '1px solid #2a2b3d',
            padding: '8px 18px', borderRadius: 8, fontSize: 13, cursor: 'pointer'
          }}>← Back to Datasets</button>
          <div style={{ fontSize: 12, color: '#5a5b72' }}>Review each layer then start the pipeline when ready.</div>
          <button onClick={handleStartPipeline} disabled={ingesting} style={{
            background: ingesting ? '#4a4c8a' : '#6366f1', color: '#fff', border: 'none',
            padding: '9px 20px', borderRadius: 8, fontSize: 13, fontWeight: 600,
            cursor: ingesting ? 'default' : 'pointer',
            display: 'flex', alignItems: 'center', gap: 6
          }}>
            {ingesting ? '⏳ Ingesting…' : 'Start Pipeline → Ingest to Bronze'}
          </button>
        </div>
      </div>
    </div>
  )
}
