import { useState, useEffect } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'

const API = 'http://localhost:4000/api'

const iconDashboard = (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>
    <rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>
  </svg>
)
const iconProjects = (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M2 7a2 2 0 012-2h4l2 3h8a2 2 0 012 2v7a2 2 0 01-2 2H4a2 2 0 01-2-2z"/>
  </svg>
)
const iconDocs = (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
    <polyline points="14 2 14 8 20 8"/>
    <line x1="16" y1="13" x2="8" y2="13"/>
    <line x1="16" y1="17" x2="8" y2="17"/>
  </svg>
)
const iconSettings = (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3"/>
    <path d="M19.07 4.93l-1.41 1.41M4.93 4.93l1.41 1.41M12 2v2M12 20v2M20 12h2M2 12h2M19.07 19.07l-1.41-1.41M4.93 19.07l1.41-1.41"/>
  </svg>
)

const Logo = () => (
  <div style={{ width:30, height:30, borderRadius:7, flexShrink:0, background:'#f5822a', display:'flex', alignItems:'center', justifyContent:'center' }}>
    <svg width="18" height="16" viewBox="0 0 18 16" fill="none">
      {/* girdle top bar - solid white outline */}
      <polygon points="3,7 9,3 15,7" fill="none" stroke="white" strokeWidth="0.8"/>
      {/* top facets - slightly visible */}
      <polygon points="3,7 9,3 9,5" fill="rgba(255,255,255,0.15)"/>
      <polygon points="15,7 9,3 9,5" fill="rgba(255,255,255,0.25)"/>
      <polygon points="3,7 15,7 9,5" fill="rgba(255,255,255,0.1)"/>
      {/* main body left - solid white */}
      <polygon points="3,7 9,5 9,14" fill="rgba(255,255,255,0.85)"/>
      {/* main body right - bright white */}
      <polygon points="15,7 9,5 9,14" fill="white"/>
      {/* bottom left */}
      <polygon points="3,7 6,11 9,14" fill="rgba(255,255,255,0.7)"/>
      {/* bottom right */}
      <polygon points="15,7 12,11 9,14" fill="rgba(255,255,255,0.9)"/>
    </svg>
  </div>
)

// ── Projects modal ────────────────────────────────────────────────────────────
function ProjectsModal({ onClose }) {
  const navigate = useNavigate()
  const [projects, setProjects] = useState([])
  const [loading,  setLoading]  = useState(true)
  const slugify = name => name?.toLowerCase().replace(/\s+/g, '-') || 'project'

  useEffect(() => {
    fetch(`${API}/projects?sort=recent`)
      .then(r => r.json()).catch(() => [])
      .then(d => { setProjects(Array.isArray(d) ? d : []); setLoading(false) })
  }, [])

  return (
    <div style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.65)', zIndex:1000, display:'flex', alignItems:'center', justifyContent:'center' }}
      onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{ width:'56vw', maxWidth:680, maxHeight:'72vh', background:'#fffdf9', border:'1px solid #e6d7c7', borderRadius:14, overflow:'hidden', display:'flex', flexDirection:'column' }}>
        <div style={{ padding:'16px 24px', borderBottom:'1px solid #f3e4d3', display:'flex', justifyContent:'space-between', alignItems:'center' }}>
          <span style={{ fontWeight:700, fontSize:15, color:'#1d2b36' }}>Existing Projects</span>
          <button onClick={onClose} style={{ background:'none', border:'none', color:'#6f756f', fontSize:20, cursor:'pointer', lineHeight:1 }}>×</button>
        </div>
        <div style={{ overflowY:'auto', padding:'12px 16px', display:'flex', flexDirection:'column', gap:8 }}>
          {loading && <p style={{ color:'#8b8b83', padding:16, fontSize:13 }}>Loading…</p>}
          {!loading && projects.length === 0 && (
            <p style={{ color:'#8b8b83', padding:16, fontSize:13 }}>No projects yet. Create your first one from the dashboard.</p>
          )}
          {projects.map(p => (
            <button key={p.project_id}
              onClick={() => { onClose(); navigate(`/project/${slugify(p.name)}/connect`) }}
              style={{ background:'#ffffff', border:'1px solid #eadbca', borderRadius:10, padding:'14px 18px', textAlign:'left', cursor:'pointer', transition:'border-color 0.15s' }}
              onMouseEnter={e => e.currentTarget.style.borderColor = '#f5822a'}
              onMouseLeave={e => e.currentTarget.style.borderColor = '#252636'}
            >
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                <div>
                  <div style={{ fontWeight:600, fontSize:14, color:'#1d2b36', marginBottom:3 }}>{p.name}</div>
                  <div style={{ fontSize:11.5, color:'#8b8b83' }}>
                    {p.domain} · {p.environment} · {new Date(p.created_at).toLocaleString()}
                  </div>
                </div>
                <span style={{ fontSize:11, color:'#d86518', flexShrink:0, marginLeft:16 }}>Open →</span>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Sidebar ───────────────────────────────────────────────────────────────────
export default function Sidebar() {
  const { pathname } = useLocation()
  const [showProjects, setShowProjects] = useState(false)

  const isActive = (to) => {
    if (to === '/') return pathname === '/'
    return pathname.startsWith(to)
  }

  return (
    <>
      <aside style={{ width:200, minHeight:'100vh', height:'100%', background:'#fffaf3', borderRight:'1px solid #f3e4d3', display:'flex', flexDirection:'column', flexShrink:0 }}>
        {/* Logo */}
        <div style={{ height:52, padding:'0 16px', flexShrink:0, display:'flex', alignItems:'center', gap:10, borderBottom:'1px solid #f3e4d3' }}>
          <Logo />
          <span style={{ fontWeight:700, fontSize:15, color:'#e8e9f0', letterSpacing:'0.06em' }}>AURUM</span>
        </div>

        {/* Nav */}
        <nav style={{ flex:1, padding:'8px 8px', overflowY:'auto' }}>

          <NavLink to="/" style={{
            display:'flex', alignItems:'center', gap:10, padding:'8px 10px', borderRadius:7, marginBottom:2,
            color: isActive('/') ? '#d86518' : '#6f756f',
            background: isActive('/') ? 'rgba(245,130,42,0.15)' : 'transparent',
            fontWeight: isActive('/') ? 600 : 400,
            fontSize:13.5, textDecoration:'none', transition:'all 0.15s',
          }}>
            <span style={{ flexShrink:0, color: isActive('/') ? '#f5822a' : 'inherit' }}>{iconDashboard}</span>
            Home
          </NavLink>

          {/* Projects — opens modal */}
          <button onClick={() => setShowProjects(true)} style={{
            width:'100%', display:'flex', alignItems:'center', gap:10, padding:'8px 10px',
            borderRadius:7, marginBottom:2, border:'none', cursor:'pointer',
            background:'transparent', color:'#6f756f', fontWeight:400,
            fontSize:13.5, textAlign:'left', transition:'all 0.15s',
          }}
            onMouseEnter={e => { e.currentTarget.style.background='rgba(245,130,42,0.08)'; e.currentTarget.style.color='#1d2b36' }}
            onMouseLeave={e => { e.currentTarget.style.background='transparent'; e.currentTarget.style.color='#6f756f' }}
          >
            <span style={{ flexShrink:0 }}>{iconProjects}</span>
            <span style={{ flex:1 }}>Projects</span>
            <span style={{ fontSize:11, color:'#5a5b72' }}>→</span>
          </button>

          <NavLink to="/docs" style={({ isActive: a }) => ({
            display:'flex', alignItems:'center', gap:10, padding:'8px 10px', borderRadius:7, marginBottom:2,
            color: a ? '#d86518' : '#6f756f',
            background: a ? 'rgba(245,130,42,0.15)' : 'transparent',
            fontWeight: a ? 600 : 400,
            fontSize:13.5, textDecoration:'none', transition:'all 0.15s',
          })}>
            <span style={{ flexShrink:0 }}>{iconDocs}</span>
            Documentation
          </NavLink>

        </nav>

        {/* Settings */}
        <div style={{ padding:'8px 8px', borderTop:'1px solid #f3e4d3' }}>
          <NavLink to="/settings" style={({ isActive: a }) => ({
            display:'flex', alignItems:'center', gap:10, padding:'8px 10px',
            borderRadius:7, textDecoration:'none', fontSize:13.5, transition:'all 0.15s',
            color: a ? '#d86518' : '#6f756f',
            background: a ? 'rgba(245,130,42,0.15)' : 'transparent',
          })}>
            <span style={{ flexShrink:0 }}>{iconSettings}</span>
            Settings
          </NavLink>
        </div>
      </aside>

      {showProjects && <ProjectsModal onClose={() => setShowProjects(false)} />}
    </>
  )
}
