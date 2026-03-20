import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ExternalLink } from 'lucide-react'
import { authApi, userApi, zohoAuthApi } from '../services/api'
import { useAuth } from '../context/AuthContext'
import GuidanceNote from '../components/GuidanceNote'

type Step = 'account' | 'zoho' | 'connect'

export default function Setup() {
  const navigate = useNavigate()
  const { saveToken } = useAuth()
  const [step, setStep] = useState<Step>('account')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const [account, setAccount] = useState({ name: '', email: '', password: '' })
  const [zoho, setZoho] = useState({
    portal_name: '',
    project_id: '',
    webhook_secret: '',
    poll_interval_seconds: 60,
  })

  // Step 1 → create account, get JWT
  const handleCreateAccount = async () => {
    setLoading(true)
    setError('')
    try {
      const resp = await authApi.setup({
        user: account,
        zoho: {
          portal_name: 'pending',
          project_id: 'pending',
        },
      })
      saveToken(resp.data.access_token)
      setStep('zoho')
    } catch (e: any) {
      if (e.response?.status === 409) {
        // Account already exists — send to login
        navigate('/login', { replace: true })
        return
      }
      setError(e.response?.data?.detail || 'Account creation failed')
    } finally {
      setLoading(false)
    }
  }

  // Step 2 → save Zoho project details
  const handleSaveZoho = async () => {
    setLoading(true)
    setError('')
    try {
      await userApi.updateZoho(zoho)
      setStep('connect')
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Failed to save Zoho config')
    } finally {
      setLoading(false)
    }
  }

  // Step 3 → redirect to Zoho OAuth
  const handleConnectZoho = async () => {
    setLoading(true)
    setError('')
    try {
      const resp = await zohoAuthApi.getAuthUrl()
      window.location.href = resp.data.url
    } catch (e: any) {
      setError('Failed to get Zoho auth URL')
      setLoading(false)
    }
  }

  const handleSkipConnect = () => {
    navigate('/')
  }

  const STEPS: Step[] = ['account', 'zoho', 'connect']
  const STEP_LABELS = { account: 'Account', zoho: 'Zoho Project', connect: 'Connect Zoho' }
  const currentIdx = STEPS.indexOf(step)

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
      <div className="w-full max-w-lg">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900">AutoDev</h1>
          <p className="text-gray-500 mt-2">Product Lifecycle Automation</p>
        </div>

        <div className="bg-white rounded-xl shadow-lg p-8">
          {/* Step indicators */}
          <div className="flex items-center gap-2 mb-8">
            {STEPS.map((s, i) => (
              <div key={s} className="flex items-center gap-2">
                <div className={`h-7 w-7 rounded-full flex items-center justify-center text-sm font-bold ${
                  i < currentIdx
                    ? 'bg-green-500 text-white'
                    : step === s
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-200 text-gray-500'
                }`}>
                  {i < currentIdx ? '✓' : i + 1}
                </div>
                <span className={`text-sm ${step === s ? 'text-blue-600 font-medium' : i < currentIdx ? 'text-green-600' : 'text-gray-400'}`}>
                  {STEP_LABELS[s]}
                </span>
                {i < STEPS.length - 1 && <div className="w-6 h-px bg-gray-300" />}
              </div>
            ))}
          </div>

          {error && (
            <div className="mb-4 rounded-lg bg-red-50 border border-red-200 text-red-700 p-3 text-sm">{error}</div>
          )}

          {/* ── Step 1: Account ── */}
          {step === 'account' && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold">Create your account</h2>
              <GuidanceNote title="AutoDev Account">
                <p>This is your local AutoDev account for accessing the dashboard.</p>
              </GuidanceNote>
              {[
                { key: 'name', label: 'Full Name', type: 'text', placeholder: 'Jane Doe' },
                { key: 'email', label: 'Email', type: 'email', placeholder: 'jane@example.com' },
                { key: 'password', label: 'Password', type: 'password', placeholder: '' },
              ].map(({ key, label, type, placeholder }) => (
                <div key={key}>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
                  <input
                    type={type}
                    className="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={(account as any)[key]}
                    onChange={(e) => setAccount({ ...account, [key]: e.target.value })}
                    placeholder={placeholder}
                  />
                </div>
              ))}
              <button
                onClick={handleCreateAccount}
                disabled={!account.name || !account.email || !account.password || loading}
                className="w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {loading ? 'Creating account...' : 'Create Account →'}
              </button>
            </div>
          )}

          {/* ── Step 2: Zoho Project Details ── */}
          {step === 'zoho' && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold">Zoho Project Details</h2>
              <GuidanceNote title="Where to find these values">
                <p><strong>Portal Name:</strong> from your Zoho Projects URL —
                  <code className="bg-blue-100 px-1 rounded"> projects.zoho.com/portal/<strong>myportal</strong></code>
                </p>
                <p><strong>Project ID:</strong> open your project in Zoho Projects → the number in the URL</p>
                <p>Your Zoho email & user ID are fetched automatically after you connect in the next step.</p>
              </GuidanceNote>
              {[
                { key: 'portal_name', label: 'Portal Name', placeholder: 'mycompany' },
                { key: 'project_id', label: 'Project ID', placeholder: '123456789012' },
                { key: 'webhook_secret', label: 'Webhook Secret (optional)', placeholder: 'shared secret for webhook verification' },
              ].map(({ key, label, placeholder }) => (
                <div key={key}>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
                  <input
                    className="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={(zoho as any)[key]}
                    onChange={(e) => setZoho({ ...zoho, [key]: e.target.value })}
                    placeholder={placeholder}
                  />
                </div>
              ))}
              <button
                onClick={handleSaveZoho}
                disabled={!zoho.portal_name || !zoho.project_id || loading}
                className="w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {loading ? 'Saving...' : 'Save & Continue →'}
              </button>
            </div>
          )}

          {/* ── Step 3: Connect to Zoho ── */}
          {step === 'connect' && (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold">Connect to Zoho</h2>
              <GuidanceNote title="OAuth Authentication">
                <p>Click the button below to authorise AutoDev to read and update tasks in your Zoho Projects account.</p>
                <p>You'll be redirected to Zoho's login page and back automatically.</p>
              </GuidanceNote>

              <div className="rounded-xl border-2 border-dashed border-blue-200 p-6 text-center">
                <div className="text-4xl mb-3">🔗</div>
                <p className="text-sm text-gray-600 mb-4">
                  AutoDev needs permission to read tasks and update their status in Zoho Projects.
                </p>
                <button
                  onClick={handleConnectZoho}
                  disabled={loading}
                  className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  <ExternalLink className="h-4 w-4" />
                  {loading ? 'Redirecting...' : 'Connect to Zoho'}
                </button>
              </div>

              <button
                onClick={handleSkipConnect}
                className="w-full text-center text-sm text-gray-400 hover:text-gray-600 underline"
              >
                Skip for now (Zoho status updates won't work)
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
