import { Routes, Route, Navigate } from 'react-router-dom'
import HomePage from './pages/HomePage'
import NewProjectPage from './pages/NewProjectPage'
import DataConnectorsPage from './pages/DataConnectorsPage'
import DatasetExplorerPage from './pages/DatasetExplorerPage'
import PipelineConfigPage from './pages/PipelineConfigPage'
import BronzeLayerPage from './pages/BronzeLayerPage'
import SilverValidationPage from './pages/SilverValidationPage'
import GoldLayerPage from './pages/GoldLayerPage'
import ReportPage from './pages/ReportPage'
import DocsPage from './pages/DocsPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/new-project" element={<NewProjectPage />} />
      <Route path="/docs" element={<DocsPage />} />
      <Route path="/project/:projectId/connect" element={<DataConnectorsPage />} />
      <Route path="/project/:projectId/select" element={<DatasetExplorerPage />} />
      <Route path="/project/:projectId/pipeline-config" element={<PipelineConfigPage />} />
      <Route path="/project/:projectId/bronze" element={<BronzeLayerPage />} />
      <Route path="/project/:projectId/silver" element={<SilverValidationPage />} />
      <Route path="/project/:projectId/gold" element={<GoldLayerPage />} />
      <Route path="/project/:projectId/report" element={<ReportPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
