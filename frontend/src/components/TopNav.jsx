import { useNavigate } from 'react-router-dom'

const iconChevronLeft = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="15 18 9 12 15 6"/>
  </svg>
)

const Logo = () => (
  <div style={{ width:28, height:28, borderRadius:6, flexShrink:0, background:'#f5822a', display:'flex', alignItems:'center', justifyContent:'center' }}>
    <svg width="17" height="15" viewBox="0 0 18 16" fill="none">
      <polygon points="3,7 9,3 15,7" fill="none" stroke="white" strokeWidth="0.8"/>
      <polygon points="3,7 9,3 9,5" fill="rgba(255,255,255,0.15)"/>
      <polygon points="15,7 9,3 9,5" fill="rgba(255,255,255,0.25)"/>
      <polygon points="3,7 15,7 9,5" fill="rgba(255,255,255,0.1)"/>
      <polygon points="3,7 9,5 9,14" fill="rgba(255,255,255,0.85)"/>
      <polygon points="15,7 9,5 9,14" fill="white"/>
      <polygon points="3,7 6,11 9,14" fill="rgba(255,255,255,0.7)"/>
      <polygon points="15,7 12,11 9,14" fill="rgba(255,255,255,0.9)"/>
    </svg>
  </div>
)

/**
 * TopNav variants:
 *   - tabs mode: shows tab bar across the top
 *   - title mode: shows page title + optional badge
 *
 * Props:
 *   title        – page title text
 *   badge        – small pill next to title (e.g. "Development")
 *   tabs         – array of tab labels
 *   activeTab    – currently active tab label
 *   onTabChange  – (tab) => void
 *   backLabel    – shows a back button with this label
 *   onBack       – override navigate(-1)
 *   rightContent – JSX inserted before the right icons
 *   notifCount   – red badge on bell icon
 *   showLogo     – show logo + title before tabs (for NewProject style)
 */
export default function TopNav({
  title, badge, tabs, activeTab, onTabChange,
  backLabel, onBack, rightContent,
  showLogo = false, activeColor = '#f5822a'
}) {
  const navigate = useNavigate()

  return (
    <header style={{
      height: 52, background: '#fffaf3', borderBottom: '1px solid #f3e4d3',
      display: 'flex', alignItems: 'center', paddingInline: 18, gap: 0,
      flexShrink: 0, width: '100%'
    }}>

      {/* Back button */}
      {backLabel && (
        <>
          <button onClick={onBack || (() => navigate(-1))} style={{
            display: 'flex', alignItems: 'center', gap: 4, color: '#6f756f',
            background: 'none', border: 'none', fontSize: 12.5, cursor: 'pointer',
            padding: '4px 8px 4px 0', borderRadius: 6, whiteSpace: 'nowrap', flexShrink: 0
          }}>
            {iconChevronLeft} {backLabel}
          </button>
          <div style={{ width: 1, height: 18, background: '#2a2b3d', margin: '0 12px', flexShrink: 0 }} />
        </>
      )}

      {/* Logo for pages that show logo in topnav */}
      {showLogo && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginRight: 20, flexShrink: 0 }}>
          <Logo />
          <span style={{ fontWeight: 700, fontSize: 13.5, color: '#e8e9f0', letterSpacing: '0.04em' }}>AURUM</span>
        </div>
      )}

      {/* Tabs */}
      {tabs ? (
        <nav style={{ display: 'flex', alignItems: 'center', gap: 0, flex: 1 }}>
          {tabs.map(t => (
            <button key={t} onClick={() => onTabChange && onTabChange(t)} style={{
              background: 'none', border: 'none',
              color: activeTab === t ? '#e8e9f0' : '#8b8ca8',
              fontWeight: activeTab === t ? 600 : 400,
              fontSize: 13, padding: '0 14px', height: 52, cursor: 'pointer',
      borderBottom: activeTab === t ? `2px solid ${activeColor}` : '2px solid transparent',
              borderTop: '2px solid transparent',
              transition: 'all 0.15s', whiteSpace: 'nowrap'
            }}>{t}</button>
          ))}
        </nav>
      ) : (
        /* Title mode */
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8 }}>
          {title && <span style={{ fontWeight: 600, fontSize: 14, color: '#e8e9f0' }}>{title}</span>}
          {badge && (
            <span style={{
              background: 'rgba(245,130,42,0.18)', color: '#d86518', border: '1px solid rgba(245,130,42,0.3)',
              fontSize: 11, padding: '2px 9px', borderRadius: 20, fontWeight: 500
            }}>{badge}</span>
          )}
        </div>
      )}

      {/* Right slot */}
      {rightContent && <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginRight: 8 }}>{rightContent}</div>}

    </header>
  )
}
