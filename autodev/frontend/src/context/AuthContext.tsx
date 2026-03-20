import { createContext, useContext, useState, ReactNode } from 'react'

interface AuthContextType {
  token: string | null
  saveToken: (t: string) => void
  clearToken: () => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('autodev_token'))

  const saveToken = (t: string) => {
    localStorage.setItem('autodev_token', t)
    setToken(t)
  }

  const clearToken = () => {
    localStorage.removeItem('autodev_token')
    setToken(null)
  }

  return (
    <AuthContext.Provider value={{ token, saveToken, clearToken }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
