import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Plus, Edit2, Trash2 } from 'lucide-react'
import { projectApi, Project } from '../services/api'

export default function Projects() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)

  const fetchProjects = async () => {
    setLoading(true)
    try {
      const resp = await projectApi.list()
      setProjects(resp.data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchProjects()
  }, [])

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this project? All pipeline runs will also be deleted.')) return
    await projectApi.delete(id)
    await fetchProjects()
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Projects</h1>
          <p className="text-sm text-gray-500">Configured target repositories</p>
        </div>
        <Link
          to="/projects/new"
          className="flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-2 text-sm text-white hover:bg-blue-700"
        >
          <Plus className="h-3.5 w-3.5" />
          New Project
        </Link>
      </div>

      {loading ? (
        <p className="text-gray-400">Loading...</p>
      ) : projects.length === 0 ? (
        <div className="rounded-xl border bg-white p-12 text-center text-gray-400">
          <p className="mb-4">No projects configured yet.</p>
          <Link to="/projects/new" className="text-blue-600 hover:underline">
            Create your first project →
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <div key={project.id} className="rounded-xl border bg-white p-5">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-semibold text-gray-900">{project.name}</h3>
                  {project.description && (
                    <p className="text-sm text-gray-500 mt-1">{project.description}</p>
                  )}
                </div>
                <div className="flex gap-1">
                  <Link
                    to={`/projects/${project.id}/edit`}
                    className="rounded p-1 hover:bg-gray-100"
                  >
                    <Edit2 className="h-4 w-4 text-gray-400" />
                  </Link>
                  <button
                    onClick={() => handleDelete(project.id)}
                    className="rounded p-1 hover:bg-gray-100"
                  >
                    <Trash2 className="h-4 w-4 text-red-400" />
                  </button>
                </div>
              </div>
              <div className="mt-3 space-y-1 text-xs text-gray-500">
                {project.frontend_tech && (
                  <p>Frontend: <span className="font-medium text-gray-700">{project.frontend_tech}</span></p>
                )}
                {project.backend_tech && (
                  <p>Backend: <span className="font-medium text-gray-700">{project.backend_tech}</span></p>
                )}
                {project.base_branch && (
                  <p>Base branch: <span className="font-mono text-gray-700">{project.base_branch}</span></p>
                )}
                {project.gitlab_repo_url && (
                  <p className="truncate">GitLab: <span className="text-gray-700">{project.gitlab_repo_url}</span></p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
