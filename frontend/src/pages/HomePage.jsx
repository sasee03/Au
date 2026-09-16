import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

const API = 'http://localhost:4000/api'

const statusStyle = {
  PASS:    { background: 'rgba(34,197,94,0.15)',  color: '#22c55e', border: '1px solid rgba(34,197,94,0.3)' },
  WARNING: { background: 'rgba(245,158,11,0.15)', color: '#f59e0b', border: '1px solid rgba(245,158,11,0.3)' },
  FAILED:  { background: 'rgba(239,68,68,0.15)',  color: '#ef4444', border: '1px solid rgba(239,68,68,0.3)' },
}

// ── Documentation modal ──────────────────────────────────────────────────────
function DocModal({ onClose }) {
  const [md, setMd] = useState('Loading documentation…')
  useEffect(() => {
    fetch(`${API}/docs`)
      .then(r => r.text())
      .catch(() => '# Documentation\n\nBackend not running yet.')
      .then(setMd)
  }, [])
  // simple markdown → HTML (headings, bold, code, bullets)
  const html = md
    .replace(/^### (.+)$/gm, '<h3 style="color:#818cf8;margin:18px 0 6px">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 style="color:#a5b4fc;margin:22px 0 8px">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 style="color:#e8e9f0;margin:0 0 16px">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong style="color:#e8e9f0">$1</strong>')
    .replace(/`(.+?)`/g, '<code style="background:#1e1f2e;padding:1px 6px;border-radius:4px;font-family:monospace;color:#818cf8">$1</code>')
    .replace(/^- (.+)$/gm, '<li style="margin:4px 0;color:#8b8ca8">$1</li>')
    .replace(/\n\n/g, '<br/><br/>')

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center'
    }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        width: '72vw', maxHeight: '80vh', background: '#13141c',
        border: '1px solid #2a2b3d', borderRadius: 14, overflow: 'hidden',
        display: 'flex', flexDirection: 'column'
      }}>
        <div style={{ padding: '16px 24px', borderBottom: '1px solid #1e1f2e', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontWeight: 700, fontSize: 15, color: '#e8e9f0' }}>AURUM Documentation</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#8b8ca8', fontSize: 20, cursor: 'pointer', lineHeight: 1 }}>×</button>
        </div>
        <div style={{ padding: '24px 28px', overflowY: 'auto', lineHeight: 1.7 }}
          dangerouslySetInnerHTML={{ __html: html }} />
      </div>
    </div>
  )
}

// ── Existing Projects modal ───────────────────────────────────────────────────
function ProjectsModal({ onClose, recentOnly }) {
  const navigate = useNavigate()
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API}/projects${recentOnly ? '?sort=recent' : ''}`)
      .then(r => r.json())
      .catch(() => [])
      .then(d => { setProjects(Array.isArray(d) ? d : []); setLoading(false) })
  }, [recentOnly])

  const slugify = name => name?.toLowerCase().replace(/\s+/g, '-') || 'project'

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        width: '60vw', maxHeight: '75vh', background: '#13141c',
        border: '1px solid #2a2b3d', borderRadius: 14, overflow: 'hidden', display: 'flex', flexDirection: 'column'
      }}>
        <div style={{ padding: '16px 24px', borderBottom: '1px solid #1e1f2e', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontWeight: 700, fontSize: 15, color: '#e8e9f0' }}>{recentOnly ? 'Recent Runs' : 'Existing Projects'}</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#8b8ca8', fontSize: 20, cursor: 'pointer' }}>×</button>
        </div>
        <div style={{ overflowY: 'auto', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {loading && <p style={{ color: '#5a5b72', padding: 16 }}>Loading…</p>}
          {!loading && projects.length === 0 && <p style={{ color: '#5a5b72', padding: 16 }}>No projects found. Connect to the backend.</p>}
          {projects.map(p => (
            <button key={p.project_id} onClick={() => { onClose(); navigate(`/project/${slugify(p.name)}/bronze`) }}
              style={{
                background: '#1a1b25', border: '1px solid #252636', borderRadius: 10,
                padding: '14px 18px', textAlign: 'left', cursor: 'pointer', transition: 'all 0.15s'
              }}
              onMouseEnter={e => e.currentTarget.style.borderColor = '#6366f1'}
              onMouseLeave={e => e.currentTarget.style.borderColor = '#252636'}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14, color: '#e8e9f0', marginBottom: 3 }}>{p.name}</div>
                  <div style={{ fontSize: 11.5, color: '#5a5b72' }}>
                    {p.domain} · {p.environment} · {new Date(p.created_at).toLocaleString()}
                  </div>
                  {p.description && <div style={{ fontSize: 11.5, color: '#8b8ca8', marginTop: 4 }}>{p.description}</div>}
                </div>
                <span style={{ fontSize: 11, color: '#6366f1' }}>Open →</span>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function HomePage() {
  const navigate = useNavigate()
  const [modal, setModal] = useState(null) // null | 'docs' | 'existing' | 'recent'
  const [projects, setProjects] = useState([])

  useEffect(() => {
    fetch(`${API}/projects?sort=recent&limit=4`)
      .then(r => r.json())
      .catch(() => [
        { project_id: '1', name: 'Retail Analytics',  created_at: new Date(Date.now() - 2*3600000).toISOString(), domain: 'Retail',   environment: 'Development', status: 'PASS' },
        { project_id: '2', name: 'Finance Pipeline',  created_at: new Date(Date.now() - 86400000).toISOString(),  domain: 'Finance',  environment: 'QA',          status: 'WARNING' },
        { project_id: '3', name: 'Supply Chain',      created_at: new Date(Date.now() - 3*86400000).toISOString(),domain: 'Other',    environment: 'Production',  status: 'FAILED' },
        { project_id: '4', name: 'Sales Warehouse',   created_at: new Date(Date.now() - 5*86400000).toISOString(),domain: 'Retail',   environment: 'Development', status: 'PASS' },
      ])
      .then(d => setProjects(Array.isArray(d) ? d.slice(0, 4) : []))
  }, [])

  const slugify = name => name?.toLowerCase().replace(/\s+/g, '-') || 'project'

  const timeAgo = iso => {
    const diff = Date.now() - new Date(iso).getTime()
    const h = Math.floor(diff / 3600000)
    if (h < 24) return `${h}h ago`
    return `${Math.floor(h / 24)}d ago`
  }

  return (
    <div style={{ width: '100%', height: '100vh', background: '#f7f1e8', overflow: 'hidden' }}>
      <main style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-start', padding: '112px 10% 36px', overflow: 'auto' }}>
        {/* Hero */}
        <div style={{ textAlign: 'center', marginBottom: 68, width: '100%' }}>
          <p style={{ fontSize: 11, letterSpacing: '0.22em', color: '#5a5b72', textTransform: 'uppercase', marginBottom: 18 }}>
            Enterprise Data Quality Operating System
          </p>
          <h1 style={{
            fontSize: 80, fontWeight: 900, letterSpacing: '-3px', marginBottom: 14, lineHeight: 1,
            background: 'linear-gradient(135deg, #fffaf3 35%, #ffc08f 66%, #f5822a 100%)',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text'
          }}>AURUM</h1>
          <p style={{ fontSize: 14.5, color: '#8b8ca8', marginBottom: 36 }}>
            Autonomous End-to-End Data Correctness &amp; Business Trust Engine
          </p>

          <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
            <button onClick={() => navigate('/new-project')} style={{
              background: '#f5822a', color: '#fff', border: 'none',
              padding: '10px 22px', borderRadius: 8, fontWeight: 600, fontSize: 13.5,
              cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6
            }}>+ New Project</button>

            <button onClick={() => setModal('existing')} style={{
              background: 'transparent', color: '#6f756f', border: '1px solid #f5822a',
              padding: '10px 18px', borderRadius: 8, fontWeight: 500, fontSize: 13.5, cursor: 'pointer'
            }}>Open Existing Project</button>

            <button onClick={() => setModal('recent')} style={{
              background: 'transparent', color: '#6f756f', border: '1px solid #f5822a',
              padding: '10px 18px', borderRadius: 8, fontWeight: 500, fontSize: 13.5, cursor: 'pointer'
            }}>Recent Runs</button>

            <button onClick={() => setModal('docs')} style={{
              background: 'transparent', color: '#6f756f', border: '1px solid #f5822a',
              padding: '10px 18px', borderRadius: 8, fontWeight: 500, fontSize: 13.5, cursor: 'pointer'
            }}>Documentation</button>
          </div>
        </div>

        {/* Recent Projects grid */}
        <div style={{ width: '100%', maxWidth: 1210 }}>
          <p style={{ fontSize: 10.5, letterSpacing: '0.16em', color: '#5a5b72', textTransform: 'uppercase', marginBottom: 12 }}>
            Recent Projects
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
            {projects.map(p => {
              const s = p.status || 'PASS'
              return (
                <button key={p.project_id || p.name}
                  onClick={() => navigate(`/project/${slugify(p.name)}/bronze`)}
                  style={{
                    background: '#ffffff', border: '1px solid #747985',
                    borderRadius: 10, padding: '16px', textAlign: 'left', cursor: 'pointer',
                    transition: 'border-color 0.15s, background 0.15s'
                  }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = '#f5822a'; e.currentTarget.style.background = '#fffaf3' }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = '#747985'; e.currentTarget.style.background = '#ffffff' }}
                >
                  <div style={{ fontWeight: 600, fontSize: 13.5, color: '#1d2b36', marginBottom: 4 }}>{p.name}</div>
                  <div style={{ fontSize: 11.5, color: '#8b8b83', marginBottom: 14 }}>
                    {p.created_at ? timeAgo(p.created_at) : '—'} · {p.domain || '—'}
                  </div>
                  <span style={{ fontSize: 10.5, fontWeight: 700, padding: '3px 8px', borderRadius: 5, ...(statusStyle[s] || statusStyle.PASS) }}>
                    {s}
                  </span>
                </button>
              )
            })}
          </div>
        </div>
      </main>

      {modal === 'docs'     && <DocModal onClose={() => setModal(null)} />}
      {modal === 'existing' && <ProjectsModal onClose={() => setModal(null)} recentOnly={false} />}
      {modal === 'recent'   && <ProjectsModal onClose={() => setModal(null)} recentOnly={true} />}
    </div>
  )
}
