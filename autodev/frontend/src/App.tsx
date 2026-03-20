import { Routes, Route, Navigate } from 'react-router-dom'
import Setup from './pages/Setup'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Projects from './pages/Projects'
import ProjectForm from './pages/ProjectForm'
import PipelineDetail from './pages/PipelineDetail'
import Settings from './pages/Settings'
import ZohoCallback from './pages/ZohoCallback'
import GitHubCallback from './pages/GitHubCallback'
import Layout from './components/Layout'
import { useAuth } from './context/AuthContext'

export default function App() {
  const { token } = useAuth()

  return (
    <Routes>
      <Route path="/zoho-callback" element={<ZohoCallback />} />
      <Route path="/github-callback" element={<GitHubCallback />} />

      {!token ? (
        <>
          <Route path="/login" element={<Login />} />
          <Route path="/setup" element={<Setup />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </>
      ) : (
        <Route
          path="*"
          element={
            <Layout>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/projects" element={<Projects />} />
                <Route path="/projects/new" element={<ProjectForm />} />
                <Route path="/projects/:id/edit" element={<ProjectForm />} />
                <Route path="/pipelines/:runId" element={<PipelineDetail />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="/setup" element={<Navigate to="/" replace />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Layout>
          }
        />
      )}
    </Routes>
  )
}
