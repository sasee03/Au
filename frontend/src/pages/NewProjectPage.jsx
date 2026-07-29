import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Sidebar from '../components/Sidebar'

const API = 'http://localhost:4000/api'

export default function NewProjectPage() {
  const navigate = useNavigate()
  const [projectName, setProjectName] = useState('')
  const [domain, setDomain]           = useState('Retail')
  const [description, setDescription] = useState('')
  const [environment, setEnvironment] = useState('Development')
  const [saving, setSaving]           = useState(false)
  const [error, setError]             = useState('')

  const domains      = ['Retail', 'Finance', 'Healthcare', 'Other']
  const environments = ['Development', 'QA', 'Production']

  const slugify = name => name.toLowerCase().replace(/\s+/g, '-') || 'project'

  const handleContinue = async () => {
    if (!projectName.trim()) { setError('Project name is required.'); return }
    setSaving(true); setError('')
    try {
      const res = await fetch(`${API}/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: projectName.trim(), domain, description, environment })
      })
      if (!res.ok) throw new Error(await res.text())
      const proj = await res.json()
      // store project_id in sessionStorage so downstream pages can use it
      sessionStorage.setItem('aurum_project_id', proj.project_id)
      sessionStorage.setItem('aurum_project_name', proj.name)
      navigate(`/project/${slugify(proj.name)}/connect`)
    } catch (e) {
      // backend not running yet — still navigate so frontend works standalone
      sessionStorage.setItem('aurum_project_name', projectName.trim())
      navigate(`/project/${slugify(projectName.trim())}/connect`)
    } finally {
      setSaving(false)
    }
  }

  const labelStyle = {
    fontSize: 10.5, fontWeight: 600, letterSpacing: '0.1em', color: '#8b8ca8',
    textTransform: 'uppercase', display: 'block', marginBottom: 8
  }
  const inputStyle = {
    width: '100%', background: '#0d0e14', border: '1px solid #2a2b3d',
    borderRadius: 8, padding: '9px 13px', color: '#e8e9f0', fontSize: 13.5,
    outline: 'none', transition: 'border-color 0.15s'
  }

  return (
    <div style={{ display: 'flex', width: '100%', height: '100vh', background: '#0d0e14', overflow: 'hidden' }}>
      <Sidebar />

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Top bar */}
        <header style={{
          height: 52, background: '#0f1018', borderBottom: '1px solid #1e1f2e',
          display: 'flex', alignItems: 'center', paddingInline: 18, gap: 10, flexShrink: 0
        }}>
          <span style={{ fontWeight: 600, fontSize: 13.5, color: '#e8e9f0' }}>New Project</span>
        </header>

        <main style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '32px 40px', overflow: 'auto' }}>
          <div style={{ width: '100%', maxWidth: 520 }}>
            <h2 style={{ fontSize: 24, fontWeight: 700, color: '#e8e9f0', marginBottom: 5 }}>Create Project</h2>
            <p style={{ color: '#8b8ca8', fontSize: 13, marginBottom: 28 }}>
              Define the project identity before connecting any data source.
            </p>

            <div style={{ background: '#13141c', border: '1px solid #2a2b3d', borderRadius: 12, padding: '24px 26px', display: 'flex', flexDirection: 'column', gap: 20 }}>

              {/* Project Name */}
              <div>
                <label style={labelStyle}>Project Name</label>
                <input
                  placeholder="e.g. Retail Analytics Q4 2024"
                  value={projectName}
                  onChange={e => { setProjectName(e.target.value); setError('') }}
                  style={{ ...inputStyle, borderColor: error ? '#ef4444' : '#2a2b3d' }}
                  onFocus={e => e.target.style.borderColor = '#6366f1'}
                  onBlur={e => e.target.style.borderColor = error ? '#ef4444' : '#2a2b3d'}
                />
                {error && <p style={{ fontSize: 11.5, color: '#ef4444', marginTop: 5 }}>{error}</p>}
              </div>

              {/* Business Domain */}
              <div>
                <label style={labelStyle}>Business Domain</label>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {domains.map(d => (
                    <button key={d} onClick={() => setDomain(d)} style={{
                      padding: '6px 16px', borderRadius: 20, fontSize: 13, fontWeight: 500,
                      border: domain === d ? '1px solid #6366f1' : '1px solid #2a2b3d',
                      background: domain === d ? 'rgba(99,102,241,0.18)' : 'transparent',
                      color: domain === d ? '#818cf8' : '#8b8ca8', cursor: 'pointer', transition: 'all 0.15s'
                    }}>{d}</button>
                  ))}
                </div>
              </div>

              {/* Description */}
              <div>
                <label style={labelStyle}>Description</label>
                <textarea
                  placeholder="Describe what this pipeline validates — e.g. validates Bronze → Gold correctness for retail orders & inventory."
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  rows={4}
                  style={{
                    ...inputStyle, resize: 'vertical',
                    fontFamily: 'ui-monospace, Consolas, monospace',
                    lineHeight: 1.65, fontSize: 13, color: description ? '#e8e9f0' : '#5a5b72'
                  }}
                  onFocus={e => e.target.style.borderColor = '#6366f1'}
                  onBlur={e => e.target.style.borderColor = '#2a2b3d'}
                />
              </div>

              {/* Environment */}
              <div>
                <label style={labelStyle}>Environment</label>
                <div style={{ display: 'flex', gap: 8 }}>
                  {environments.map(env => (
                    <button key={env} onClick={() => setEnvironment(env)} style={{
                      padding: '6px 16px', borderRadius: 20, fontSize: 13, fontWeight: 500,
                      border: environment === env ? '1px solid #6366f1' : '1px solid #2a2b3d',
                      background: environment === env ? 'rgba(99,102,241,0.18)' : 'transparent',
                      color: environment === env ? '#818cf8' : '#8b8ca8', cursor: 'pointer', transition: 'all 0.15s'
                    }}>{env}</button>
                  ))}
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 20 }}>
              <button onClick={() => navigate('/')} style={{
                background: 'transparent', color: '#8b8ca8', border: '1px solid #2a2b3d',
                padding: '9px 22px', borderRadius: 8, fontSize: 13.5, cursor: 'pointer'
              }}>Cancel</button>
              <button onClick={handleContinue} disabled={saving} style={{
                background: saving ? '#4a4c8a' : '#6366f1', color: '#fff', border: 'none',
                padding: '9px 22px', borderRadius: 8, fontSize: 13.5, fontWeight: 600,
                cursor: saving ? 'default' : 'pointer', transition: 'background 0.15s'
              }}>
                {saving ? 'Saving…' : 'Continue →'}
              </button>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
