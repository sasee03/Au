import { useEffect } from 'react'

export default function QualityDetailsModal({ issues, onClose }) {
  useEffect(() => {
    const closeOnEscape = event => {
      if (event.key === 'Escape') onClose()
    }
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', closeOnEscape)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', closeOnEscape)
    }
  }, [onClose])

  return (
    <div style={{
        position: 'fixed',
        inset: 0,
        zIndex: 2500,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '3vh 3vw',
        background: 'rgba(29, 43, 54, 0.58)',
        backdropFilter: 'blur(2px)',
      }}>
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="dq-details-title"
        style={{
          width: 'min(1500px, 96vw)',
          height: '94vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          background: '#f7f1e8',
          border: '1px solid #e6d7c7',
          borderRadius: 10,
          boxShadow: '0 24px 80px rgba(13, 24, 34, 0.3)',
        }}
      >
        <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, padding: '18px 24px', background: '#fffdf9', borderBottom: '1px solid #e6d7c7', flexShrink: 0 }}>
          <div>
            <h1 id="dq-details-title" style={{ margin: 0, color: '#1d2b36', fontSize: 22 }}>Data Quality Check Details</h1>
            <p style={{ color: '#6f756f', margin: '5px 0 0', fontSize: 13 }}>Failed checks and the source rows that did not pass.</p>
          </div>
          <button onClick={onClose} aria-label="Close details" style={{ width: 38, height: 38, border: '1px solid #e6d7c7', borderRadius: 6, background: '#fffaf3', color: '#1d2b36', fontSize: 22, lineHeight: 1, cursor: 'pointer', flexShrink: 0 }}>×</button>
        </header>

        <div style={{ flex: 1, overflowY: 'auto', padding: '18px 24px 24px' }}>
          {issues.length === 0 ? (
            <p style={{ color: '#6f756f' }}>No failed checks in this report.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {issues.map((issue, index) => {
                const failedRows = issue.failed_rows || []
                const columns = Object.keys(failedRows[0]?.values || {})
                return (
                  <section key={`${issue.table_name}-${issue.column_name}-${issue.check_name}-${index}`} style={{ background: '#fffdf9', border: '1px solid #e6d7c7', borderRadius: 8, overflow: 'hidden', boxShadow: '0 4px 16px rgba(29,43,54,0.06)' }}>
                    <div style={{ padding: '14px 16px', borderBottom: '1px solid #eadbca', display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '6px 18px' }}>
                      <strong style={{ color: '#1d2b36', fontSize: 15 }}>{issue.check_name || issue.rule}</strong>
                      <span style={{ color: '#6f756f', fontSize: 12 }}>{issue.table_name} · {issue.column_name}</span>
                      <span style={{ marginLeft: 'auto', color: '#a84f16', fontSize: 12, fontWeight: 600 }}>{issue.bad_records.toLocaleString()} failed · {issue.bad_pct.toFixed(2)}%</span>
                    </div>
                    {issue.failed_rows_truncated && <p style={{ margin:0, padding:'9px 16px', color:'#6f756f', fontSize:11, borderBottom:'1px solid #eadbca' }}>Showing up to 100 matching source rows; the failed count above is exact.</p>}
                    {failedRows.length ? (
                      <div style={{ overflow: 'auto', maxHeight: 520 }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                          <thead style={{ position: 'sticky', top: 0, background: '#f7eadb', zIndex: 1 }}>
                            <tr>
                              <th style={{ padding: '9px 12px', textAlign: 'left', color: '#633315', whiteSpace: 'nowrap' }}>Row</th>
                              {columns.map(column => {
                                const impacted = column === issue.column_name
                                return (
                                  <th
                                    key={column}
                                    style={{
                                      padding: '9px 12px',
                                      textAlign: 'left',
                                      color: impacted ? '#8f3f08' : '#633315',
                                      background: impacted ? '#f4c995' : '#f7eadb',
                                      whiteSpace: 'nowrap',
                                    }}
                                  >
                                    {column}{impacted ? ' · Impacted' : ''}
                                  </th>
                                )
                              })}
                            </tr>
                          </thead>
                          <tbody>
                            {failedRows.map(row => (
                              <tr key={row.row_number} style={{ borderTop: '1px solid #eadbca' }}>
                                <td style={{ padding: '8px 12px', color: '#806f61', whiteSpace: 'nowrap' }}>{row.row_number}</td>
                                {columns.map(column => {
                                  const impacted = column === issue.column_name
                                  return (
                                    <td
                                      key={column}
                                      style={{
                                        padding: '8px 12px',
                                        color: impacted ? '#713507' : '#3b312a',
                                        background: impacted ? '#fff0dc' : '#fffdf9',
                                        fontWeight: impacted ? 700 : 400,
                                        whiteSpace: 'nowrap',
                                        maxWidth: 360,
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                      }}
                                      title={String(row.values[column] ?? '')}
                                    >
                                      {row.values[column] == null ? 'NULL' : String(row.values[column])}
                                    </td>
                                  )
                                })}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p style={{ margin: 0, padding: 14, color: '#6f756f', fontSize: 12 }}>No source rows were attached to this check.</p>
                    )}
                  </section>
                )
              })}
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
