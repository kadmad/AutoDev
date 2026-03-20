import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { githubAuthApi } from '../services/api'
import { CheckCircle, XCircle, Loader } from 'lucide-react'

type State = 'loading' | 'success' | 'error'

export default function GitHubCallback() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [state, setState] = useState<State>('loading')
  const [message, setMessage] = useState('')

  useEffect(() => {
    const code = searchParams.get('code')
    const error = searchParams.get('error')

    if (error) {
      setState('error')
      setMessage(`GitHub declined the authorisation: ${error}`)
      return
    }

    if (!code) {
      setState('error')
      setMessage('No authorisation code received from GitHub.')
      return
    }

    githubAuthApi
      .exchangeCode(code)
      .then(() => {
        setState('success')
        setMessage('GitHub connected successfully!')
        setTimeout(() => navigate('/'), 2000)
      })
      .catch((e: any) => {
        setState('error')
        setMessage(e.response?.data?.detail || 'Token exchange failed. Please try again.')
      })
  }, []) // run once on mount

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-200 flex items-center justify-center">
      <div className="bg-white rounded-xl shadow-lg p-10 text-center max-w-sm w-full">
        {state === 'loading' && (
          <>
            <Loader className="h-12 w-12 text-gray-700 animate-spin mx-auto mb-4" />
            <h2 className="text-lg font-semibold text-gray-800">Connecting to GitHub…</h2>
            <p className="text-sm text-gray-500 mt-2">Exchanging authorisation code for tokens</p>
          </>
        )}
        {state === 'success' && (
          <>
            <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-4" />
            <h2 className="text-lg font-semibold text-gray-800">GitHub Connected!</h2>
            <p className="text-sm text-gray-500 mt-2">{message}</p>
            <p className="text-xs text-gray-400 mt-3">Redirecting to dashboard…</p>
          </>
        )}
        {state === 'error' && (
          <>
            <XCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
            <h2 className="text-lg font-semibold text-gray-800">Connection Failed</h2>
            <p className="text-sm text-red-600 mt-2">{message}</p>
            <div className="flex gap-2 mt-5">
              <button
                onClick={() => navigate('/projects')}
                className="flex-1 rounded-lg border px-4 py-2 text-sm hover:bg-gray-50"
              >
                Back to Projects
              </button>
              <button
                onClick={() => navigate('/')}
                className="flex-1 rounded-lg bg-gray-800 px-4 py-2 text-sm text-white hover:bg-gray-900"
              >
                Go to Dashboard
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
