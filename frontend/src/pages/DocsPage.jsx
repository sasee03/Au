import { useState } from 'react'
import Sidebar from '../components/Sidebar'

const ACCENT = '#6366f1'

const sections = [
  {
    id: 'what-is-aurum',
    title: 'What is AURUM?',
    content: `AURUM is a data pipeline platform that takes your raw data — from a CSV file or a PostgreSQL database — and progressively cleans and transforms it into business-ready outputs called KPIs.

It does this in three stages called the Bronze, Silver, and Gold layers. Each stage builds on the previous one:

Bronze is the raw data exactly as it came from the source — nothing changed, nothing removed.

Silver is the cleaned version. You describe what needs to be fixed in plain English, and AURUM writes the SQL to do it.

Gold is the business output. You describe what you want to measure, and AURUM generates the SQL queries that compute your KPIs.

You do not need to write any SQL yourself. AURUM handles the SQL generation. You review it, approve it, and execute it.`,
  },
  {
    id: 'creating-a-project',
    title: 'Creating a Project',
    steps: [
      {
        title: 'Open the dashboard',
        desc: 'When you start AURUM, the home screen opens. Click the "+ New Project" button.',
      },
      {
        title: 'Enter project details',
        desc: 'Give your project a name, choose a domain (Retail, Finance, Healthcare, etc.), and select an environment (Development, QA, or Production). Click Create Project.',
      },
      {
        title: 'You are now in the pipeline',
        desc: 'AURUM opens the Connect page, which is step one of the seven-step pipeline. The tab bar at the top shows your current position.',
      },
    ],
  },
  {
    id: 'connecting-data',
    title: 'Connecting Your Data',
    content: `The Connect page is where you tell AURUM where your data comes from. There are two options.`,
    subsections: [
      {
        title: 'Option A — Upload a CSV file',
        steps: [
          'Enter a name for your dataset in the Dataset Name field.',
          'Drag and drop your CSV file onto the upload area, or click to browse.',
          'Choose the delimiter (comma, tab, semicolon, or pipe) and encoding if needed.',
          'Click "Configure Pipeline →". AURUM immediately reads the file and creates a copy of your data in the database.',
        ],
      },
      {
        title: 'Option B — Connect to PostgreSQL',
        steps: [
          'Enter the Host, Port, Database name, Schema, Username, and Password.',
          'Click "Test Connection" to verify the details are correct.',
          'Click "Select Tables →". AURUM connects to your database and shows you a list of all tables in the schema.',
          'On the next screen (Select), tick the tables you want to process and click Continue.',
        ],
      },
    ],
  },
  {
    id: 'pipeline-config',
    title: 'Configure Pipeline',
    content: `After connecting your data, AURUM shows you the Configure Pipeline page. This is a read-only overview of what the three layers will do — Bronze, Silver, and Gold — and the six steps that make up the pipeline.

Nothing has been executed yet at this point. This page gives you a chance to review before committing.

When you are ready, click "Start Pipeline → Ingest to Bronze". AURUM copies your selected tables into the Bronze layer. For PostgreSQL sources this happens now. For CSV this already happened when you uploaded the file.

Once the ingestion completes, AURUM automatically opens the Bronze Layer page.`,
  },
  {
    id: 'bronze-layer',
    title: 'Bronze Layer',
    content: `The Bronze Layer page shows you your raw data exactly as it arrived from the source. No changes have been made — NULLs, duplicates, and inconsistencies are all preserved.

On the left is the data table showing the first rows. On the right is the information schema — the column names and their detected types. This is important: the column names shown here are the exact names the AI will use when it writes your Silver SQL.

If you selected multiple tables, a tab bar appears below the top navigation. Click any tab to switch between tables and inspect each one.

When you have reviewed the data, click "Continue to Silver →" at the bottom right.`,
  },
  {
    id: 'silver-layer',
    title: 'Silver Layer — Cleaning the Data',
    content: `The Silver Layer is where you define your cleaning rules. Each rule is a plain English instruction describing what needs to change.`,
    subsections: [
      {
        title: 'How to add rules',
        steps: [
          'Type a cleaning rule in the input box at the bottom left. For example: "Cast order_purchase_timestamp to timestamp format" or "Remove rows where customer_id is null".',
          'Press Enter or click + to add the rule. You can add as many rules as you need.',
          'Click "✦ Generate SQL". AURUM sends your rules and the column schema to the AI, which writes one SQL statement per rule.',
          'The generated SQL appears in the right panel. You can click into any SQL block and edit it directly.',
        ],
      },
      {
        title: 'Approve',
        steps: [
          'When you are happy with the SQL, click "Approve". AURUM runs the SQL as a dry run against the Bronze data — no changes are written.',
          'A preview of the transformed data appears below the rules. A badge shows how many rows would survive the cleaning.',
          'If the preview looks wrong, edit the SQL and click Approve again.',
        ],
      },
      {
        title: 'Execute',
        steps: [
          'Click "▶ Execute". AURUM runs the full CTE pipeline and creates a new Silver table in the database.',
          'The preview switches to show the actual Silver table output, along with row counts.',
          'For multi-table datasets, after executing one table the button changes to show the next table name. Click it to switch to that table and repeat the process.',
          'Once all tables are executed, the button changes to "→ Continue to Gold".',
        ],
      },
    ],
  },
  {
    id: 'gold-layer',
    title: 'Gold Layer — Business KPIs',
    content: `The Gold Layer turns your cleaned Silver data into business-ready KPI tables.`,
    subsections: [
      {
        title: 'Generating KPIs',
        steps: [
          'Type your business requirement in the input box. For example: "I need an executive sales dashboard showing revenue trends, top customers, and product performance."',
          'Click "✦ Generate KPI Plan". AURUM reads the current Silver table schemas and sends them to the AI along with your requirement.',
          'The AI returns 5 KPIs. Each one has a name and a SQL SELECT statement. KPIs the AI could not compute from your data are marked as Unavailable.',
          'Click any KPI in the left panel to view and edit its SQL in the right panel.',
        ],
      },
      {
        title: 'Building Gold tables',
        steps: [
          'Review the generated SQL. Edit any statement if needed.',
          'Click "Approve & Build Gold". AURUM executes each Ready KPI and creates a separate Gold table for each one.',
          'A preview of the first Gold table appears below.',
          'Click "Generate Report →" to proceed.',
        ],
      },
    ],
  },
  {
    id: 'report',
    title: 'Pipeline Report',
    content: `The Report page is a summary of everything that happened in the pipeline run.

It shows the source tables that were ingested, the row counts at each stage (Bronze rows in, Silver rows out, rows removed), the cleaning rules that were applied with their SQL, the KPIs that were computed, and the names of all Gold tables that were created.

The Database Table Reference section at the bottom lists every table AURUM created, with its full schema-qualified name. These are the table names you would use to connect a BI tool like Tableau, Metabase, or Power BI directly to your Gold data.

Use "↓ Export PDF" at the top right to save the report.`,
  },
  {
    id: 'opening-projects',
    title: 'Opening an Existing Project',
    content: `Your projects are saved automatically. To return to an existing one, click "Projects" in the left sidebar. A panel opens showing all your projects with their name, domain, environment, and creation time.

Click "Open →" on any project to navigate to its Connect page and continue from where you left off.

You can also click "Open Existing Project" from the home screen dashboard.`,
  },
  {
    id: 'tips',
    title: 'Tips for Better Results',
    subsections: [
      {
        title: 'Writing good cleaning rules',
        steps: [
          'Be specific about the column name: "Cast order_date to DATE" works better than "fix the date column".',
          'Reference the exact column name as shown in the information_schema panel on the Bronze page.',
          'For removing rows: "Remove rows where payment_value is null or negative".',
          'For transformations: "Convert customer_city to title case by trimming whitespace".',
          'For derived columns: "Add a column called delivery_days as the difference between order_delivered_date and order_purchase_date".',
        ],
      },
      {
        title: 'Writing a good business requirement for Gold',
        steps: [
          'Be concrete about what you want to measure: revenue, counts, averages, rankings.',
          'Mention the dimensions you care about: by product, by region, by month.',
          'The more specific the requirement, the more relevant the KPIs the AI will generate.',
          'Example: "Show monthly revenue trend, top 10 customers by order value, and average delivery time by product category."',
        ],
      },
    ],
  },
]

export default function DocsPage() {
  const [active, setActive] = useState('what-is-aurum')
  const section = sections.find(s => s.id === active)

  const renderContent = (sec) => {
    if (!sec) return null
    return (
      <div>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: '#e8e9f0', marginBottom: 6 }}>{sec.title}</h1>
        <div style={{ width: 36, height: 2, background: ACCENT, borderRadius: 2, marginBottom: 24 }} />

        {/* Plain text */}
        {sec.content && sec.content.split('\n\n').map((para, i) => (
          <p key={i} style={{ color: '#c4c5d6', fontSize: 14, lineHeight: 1.8, marginBottom: 16 }}>{para}</p>
        ))}

        {/* Top-level steps */}
        {sec.steps && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginBottom: 16 }}>
            {sec.steps.map((s, i) => (
              <div key={i} style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
                <div style={{ width: 26, height: 26, borderRadius: '50%', background: 'rgba(99,102,241,0.15)', border: '1px solid rgba(99,102,241,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, color: '#818cf8', flexShrink: 0, marginTop: 2 }}>{i + 1}</div>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14, color: '#e8e9f0', marginBottom: 3 }}>{s.title}</div>
                  <div style={{ fontSize: 13.5, color: '#8b8ca8', lineHeight: 1.65 }}>{s.desc}</div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Subsections */}
        {sec.subsections && sec.subsections.map((sub, si) => (
          <div key={si} style={{ marginBottom: 28 }}>
            <h3 style={{ fontSize: 14, fontWeight: 700, color: '#818cf8', marginBottom: 12 }}>{sub.title}</h3>
            <ol style={{ paddingLeft: 20, margin: 0 }}>
              {sub.steps.map((step, i) => (
                <li key={i} style={{ color: '#c4c5d6', fontSize: 13.5, lineHeight: 1.75, marginBottom: 8 }}>{step}</li>
              ))}
            </ol>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', width: '100%', height: '100vh', background: '#0d0e14', overflow: 'hidden' }}>
      <Sidebar />
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* Docs nav */}
        <aside style={{ width: 210, borderRight: '1px solid #1e1f2e', padding: '20px 10px', display: 'flex', flexDirection: 'column', gap: 2, overflowY: 'auto', flexShrink: 0 }}>
          <div style={{ fontSize: 10, color: '#5a5b72', letterSpacing: '0.12em', textTransform: 'uppercase', padding: '0 8px', marginBottom: 10 }}>User Guide</div>
          {sections.map(s => (
            <button key={s.id} onClick={() => setActive(s.id)} style={{
              width: '100%', textAlign: 'left', padding: '8px 12px', borderRadius: 7,
              border: 'none', cursor: 'pointer', fontSize: 13,
              background: active === s.id ? 'rgba(99,102,241,0.15)' : 'transparent',
              color: active === s.id ? '#e8e9f0' : '#8b8ca8',
              fontWeight: active === s.id ? 600 : 400,
              borderLeft: active === s.id ? `2px solid ${ACCENT}` : '2px solid transparent',
              transition: 'all 0.12s',
            }}>
              {s.title}
            </button>
          ))}
        </aside>

        {/* Content */}
        <main style={{ flex: 1, padding: '36px 48px', overflowY: 'auto', maxWidth: 780 }}>
          {renderContent(section)}
        </main>
      </div>
    </div>
  )
}
