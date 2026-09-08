import React, { useState, useEffect, useCallback, useRef } from 'react'
import {
  AppBar, Toolbar, Typography, Box, Tabs, Tab, Container,
  IconButton, Chip, Tooltip, Paper, TextField, Button,
  Alert, CircularProgress, Drawer, Dialog, DialogTitle,
  DialogContent, DialogActions,
} from '@mui/material'
import TipsAndUpdatesIcon from '@mui/icons-material/TipsAndUpdates'
import RocketLaunchIcon from '@mui/icons-material/RocketLaunch'
import CloudIcon from '@mui/icons-material/Cloud'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import ErrorIcon from '@mui/icons-material/Error'
import LockOpenIcon from '@mui/icons-material/LockOpen'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import AccountCircleIcon from '@mui/icons-material/AccountCircle'
import GoogleIcon from '@mui/icons-material/Google'
import FolderIcon from '@mui/icons-material/Folder'
import LinkIcon from '@mui/icons-material/Link'
import MenuIcon from '@mui/icons-material/Menu'
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft'
import AdvisoryPanel from './components/AdvisoryPanel'
import ScanningPanel from './components/ScanningPanel'

const DRAWER_WIDTH = 290

function TabPanel({ children, value, index }) {
  return (
    <div
      role="tabpanel"
      style={{
        width: '100%',
        display: value === index ? 'block' : 'none',
      }}
    >
      <Box sx={{ pt: 3 }}>{children}</Box>
    </div>
  )
}

export default function App() {
  const [tab, setTab] = useState(0)
  const [machineTypes, setMachineTypes] = useState([])
  const [loading, setLoading] = useState(true)
  const [project, setProject] = useState('')
  const [projectInput, setProjectInput] = useState('')
  const [authStatus, setAuthStatus] = useState(null)
  const [authChecking, setAuthChecking] = useState(false)
  const [loginInProgress, setLoginInProgress] = useState(false)
  const [loginSuccess, setLoginSuccess] = useState(false)
  const [loginError, setLoginError] = useState(null)
  const [drawerOpen, setDrawerOpen] = useState(true)
  const [demoMode, setDemoMode] = useState(false)
  const [repoUrl, setRepoUrl] = useState('')
  const [demoDialogOpen, setDemoDialogOpen] = useState(false)
  const [authMode, setAuthMode] = useState('local')
  const [oauthClientId, setOauthClientId] = useState('')
  const [signedInEmail, setSignedInEmail] = useState('')
  const [tokenInput, setTokenInput] = useState('')
  const [userToken, setUserToken] = useState(() => sessionStorage.getItem('cr_user_token') || '')
  const projectInputRef = useRef('')

  useEffect(() => {
    // Fetch config and machine types in parallel
    Promise.all([
      fetch('/api/config').then(r => r.json()).catch(() => ({ demoMode: false })),
      fetch('/api/machine-types').then(r => r.json()).catch(() => ({ machineTypes: [] })),
    ]).then(([config, mtData]) => {
      setMachineTypes(mtData.machineTypes || [])
      setLoading(false)
      if (config.authMode) setAuthMode(config.authMode)
      if (config.oauthClientId) setOauthClientId(config.oauthClientId)
      if (config.authMode === 'user' && sessionStorage.getItem('cr_user_token')) {
        setLoginSuccess(true)
        setSignedInEmail(sessionStorage.getItem('cr_user_email') || '')
      }
      if (config.demoMode) {
        setDemoMode(true)
        setRepoUrl(config.repoUrl || '')
        setProject(config.project)
        setDrawerOpen(false)
        setAuthStatus({
          authenticated: true,
          projectValid: true,
          computeApiEnabled: true,
          account: 'Cloud Run Service Account',
        })
        setLoginSuccess(true)
      }
    })
  }, [])

  const checkAuth = useCallback(async (tokenOverride) => {
    if (!projectInput.trim()) return
    setAuthChecking(true)
    try {
      const token = typeof tokenOverride === 'string' ? tokenOverride : userToken
      const resp = await fetch('/api/auth/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project: projectInput.trim(), token: token || undefined }),
      })
      const data = await resp.json()
      setAuthStatus(data)
      if (data.authenticated && data.projectValid && data.computeApiEnabled) {
        setProject(projectInput.trim())
        // Auto-close drawer when connected
        setTimeout(() => setDrawerOpen(false), 800)
      }
    } catch (e) {
      setAuthStatus({ authenticated: false, errors: ['Failed to connect to backend.'], instructions: [] })
    } finally {
      setAuthChecking(false)
    }
  }, [projectInput, userToken])

  const applyToken = useCallback(() => {
    const token = tokenInput.trim()
    if (!token) return
    setUserToken(token)
    sessionStorage.setItem('cr_user_token', token)
    setTokenInput('')
    setLoginSuccess(true)
    setLoginError(null)
    if (projectInput.trim()) {
      setTimeout(() => checkAuth(token), 100)
    }
  }, [tokenInput, projectInput, checkAuth])

  useEffect(() => { projectInputRef.current = projectInput }, [projectInput])

  // Browser-based Google sign-in (Google Identity Services token client).
  // Grants a cloud-platform scoped access token directly to this page —
  // nothing to copy/paste, no credentials ever touch the server.
  const signInWithGoogle = useCallback(() => {
    setLoginError(null)
    if (!window.google?.accounts?.oauth2) {
      setLoginError('Google sign-in library failed to load. Refresh the page and try again.')
      return
    }
    const client = window.google.accounts.oauth2.initTokenClient({
      client_id: oauthClientId,
      scope: 'openid email https://www.googleapis.com/auth/cloud-platform',
      callback: async (resp) => {
        if (resp.error || !resp.access_token) {
          setLoginError(resp.error_description || resp.error || 'Sign-in failed.')
          return
        }
        setUserToken(resp.access_token)
        sessionStorage.setItem('cr_user_token', resp.access_token)
        setLoginSuccess(true)
        setLoginError(null)
        try {
          const info = await fetch(
            `https://www.googleapis.com/oauth2/v3/tokeninfo?access_token=${encodeURIComponent(resp.access_token)}`
          ).then(r => r.json())
          if (info.email) {
            setSignedInEmail(info.email)
            sessionStorage.setItem('cr_user_email', info.email)
          }
        } catch { /* email display is best-effort */ }
        if (projectInputRef.current.trim()) {
          setTimeout(() => checkAuth(resp.access_token), 100)
        }
      },
      error_callback: (err) => {
        if (err?.type !== 'popup_closed') {
          setLoginError(err?.message || 'Sign-in was cancelled or blocked (check popup blocker).')
        }
      },
    })
    client.requestAccessToken()
  }, [oauthClientId, checkAuth])

  const handleLogin = useCallback(async () => {
    setLoginInProgress(true)
    setLoginSuccess(false)
    setLoginError(null)
    try {
      const resp = await fetch('/api/auth/login', { method: 'POST' })
      const data = await resp.json()
      if (data.success) {
        setLoginSuccess(true)
        if (projectInput.trim()) {
          setTimeout(() => checkAuth(), 500)
        }
      } else {
        setLoginError(data.message || 'Authentication failed.')
      }
    } catch (e) {
      setLoginError('Failed to connect to backend.')
    } finally {
      setLoginInProgress(false)
    }
  }, [projectInput, checkAuth])

  const isReady = authStatus?.authenticated && authStatus?.projectValid && authStatus?.computeApiEnabled
  const copyCmd = (cmd) => navigator.clipboard?.writeText(cmd)

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', bgcolor: 'background.default' }}>
      {/* App Bar */}
      <AppBar position="static" color="inherit" sx={{ bgcolor: '#fff', zIndex: 1201 }}>
        <Toolbar sx={{ gap: 1.5 }}>
          {/* Drawer toggle - hidden in demo mode */}
          {!demoMode && (
            <Tooltip title={drawerOpen ? 'Close panel' : 'Open auth panel'}>
              <IconButton onClick={() => setDrawerOpen(!drawerOpen)} edge="start" size="small">
                {drawerOpen ? <ChevronLeftIcon /> : <MenuIcon />}
              </IconButton>
            </Tooltip>
          )}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <img src="/gcp_logo.png" alt="Google Cloud" style={{ height: 32 }} />
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, ml: 0.5 }}>
              <Box sx={{ width: 3, height: 18, borderRadius: 1, bgcolor: '#4285f4' }} />
              <Box sx={{ width: 3, height: 18, borderRadius: 1, bgcolor: '#ea4335' }} />
              <Box sx={{ width: 3, height: 18, borderRadius: 1, bgcolor: '#fbbc04' }} />
              <Box sx={{ width: 3, height: 18, borderRadius: 1, bgcolor: '#34a853' }} />
            </Box>
            <Typography variant="h3" sx={{ color: '#202124', fontWeight: 500, fontSize: '1.125rem', fontFamily: '"Google Sans", "Roboto", sans-serif' }}>
              Capacity Radar
            </Typography>
          </Box>
          <Box sx={{ flexGrow: 1 }} />
          {demoMode && (
            <Chip label="☁️ Demo Mode" size="small" onClick={() => setDemoDialogOpen(true)}
              sx={{ height: 24, fontSize: '0.68rem', bgcolor: '#e8f0fe', color: '#1a73e8', fontWeight: 600, mr: 1, cursor: 'pointer', '&:hover': { bgcolor: '#d2e3fc' } }} />
          )}
          {isReady ? (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              {!demoMode && (
                <>
                  <Chip
                    icon={<CheckCircleIcon sx={{ fontSize: 14 }} />}
                    label={authStatus.account}
                    size="small"
                    color="success"
                    variant="outlined"
                    sx={{ height: 26, fontSize: '0.72rem' }}
                  />
                  <Chip
                    icon={<CloudIcon sx={{ fontSize: 14 }} />}
                    label={project}
                    size="small"
                    variant="outlined"
                    sx={{ height: 26, fontSize: '0.72rem', fontWeight: 500 }}
                  />
                </>
              )}
            </Box>
          ) : (
            <Chip
              icon={<LockOpenIcon sx={{ fontSize: 14 }} />}
              label="Not connected"
              size="small"
              color="warning"
              variant="outlined"
              onClick={() => setDrawerOpen(true)}
              sx={{ height: 26, fontSize: '0.72rem', cursor: 'pointer' }}
            />
          )}
        </Toolbar>
      </AppBar>

      <Box sx={{ display: 'flex', flex: 1 }}>
        {/* Collapsible Drawer */}
        <Drawer
          variant="persistent"
          anchor="left"
          open={drawerOpen}
          sx={{
            width: drawerOpen ? DRAWER_WIDTH : 0,
            flexShrink: 0,
            '& .MuiDrawer-paper': {
              width: DRAWER_WIDTH,
              position: 'relative',
              bgcolor: isReady ? '#e6f4ea' : '#fff',
              borderRight: 1,
              borderColor: isReady ? '#34a853' : 'divider',
              transition: 'background-color 0.3s',
            },
          }}
        >
          {/* Header */}
          <Box sx={{ p: 2, borderBottom: 1, borderColor: isReady ? '#34a85333' : 'divider' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                {isReady ? (
                  <CheckCircleIcon sx={{ color: '#34a853', fontSize: 20 }} />
                ) : (
                  <LockOpenIcon sx={{ color: '#1a73e8', fontSize: 20 }} />
                )}
                <Typography variant="subtitle2" sx={{ fontWeight: 600, color: isReady ? '#137333' : '#202124' }}>
                  {isReady ? 'Connected' : 'Authentication'}
                </Typography>
              </Box>
              <IconButton size="small" onClick={() => setDrawerOpen(false)}>
                <ChevronLeftIcon fontSize="small" />
              </IconButton>
            </Box>
            {isReady && (
              <Box sx={{ mt: 1, display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <AccountCircleIcon sx={{ fontSize: 14, color: '#137333' }} />
                  <Typography variant="caption" sx={{ color: '#137333', fontWeight: 500 }}>{authStatus.account}</Typography>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <FolderIcon sx={{ fontSize: 14, color: '#137333' }} />
                  <Typography variant="caption" sx={{ color: '#137333', fontWeight: 500 }}>{project}</Typography>
                </Box>
              </Box>
            )}
          </Box>

          {/* Auth Controls */}
          <Box sx={{ p: 2, flex: 1, overflowY: 'auto' }}>
            {/* Step 1: Authenticate */}
            <Box sx={{
              mb: 2, p: 1.5, borderRadius: 1,
              bgcolor: loginSuccess ? '#e6f4ea' : '#f8f9fa',
              border: loginSuccess ? '1px solid #34a853' : '1px solid #e8eaed',
              transition: 'all 0.3s',
            }}>
              <Typography variant="caption" sx={{ fontWeight: 600, color: '#3c4043', display: 'block', mb: 0.5 }}>
                Step 1: Authenticate
              </Typography>
              {authMode === 'user' && oauthClientId ? (
                <>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1, fontSize: '0.65rem' }}>
                    Sign in with your Google account. Everything runs with YOUR credentials on YOUR project — the server never sees or stores them.
                  </Typography>
                  <Button
                    fullWidth
                    variant={loginSuccess ? "outlined" : "contained"}
                    onClick={signInWithGoogle}
                    size="small"
                    startIcon={loginSuccess ? <CheckCircleIcon /> : <GoogleIcon />}
                    color={loginSuccess ? "success" : "primary"}
                    sx={{ fontSize: '0.72rem', textTransform: 'none' }}
                  >
                    {loginSuccess ? 'Signed in ✓ — click to refresh' : 'Sign in with Google'}
                  </Button>
                  {loginSuccess && signedInEmail && (
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.5 }}>
                      <AccountCircleIcon sx={{ fontSize: 13, color: '#137333' }} />
                      <Typography variant="caption" sx={{ color: '#137333', fontWeight: 500, fontSize: '0.65rem' }}>
                        {signedInEmail}
                      </Typography>
                    </Box>
                  )}
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5, fontSize: '0.6rem' }}>
                    Your session stays in this browser tab and expires after about 1 hour — just sign in again to refresh.
                  </Typography>
                </>
              ) : authMode === 'user' ? (
                <>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5, fontSize: '0.65rem' }}>
                    Uses YOUR Google Cloud credentials — nothing runs on our project. Get a token with one command (no install needed via Cloud Shell):
                  </Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.75 }}>
                    <code style={{ background: '#f1f3f4', padding: '2px 6px', borderRadius: 3, fontSize: '0.62rem', flex: 1 }}>
                      gcloud auth print-access-token
                    </code>
                    <IconButton size="small" onClick={() => copyCmd('gcloud auth print-access-token')} sx={{ p: 0.2 }}>
                      <ContentCopyIcon sx={{ fontSize: 12 }} />
                    </IconButton>
                  </Box>
                  <Button
                    fullWidth
                    variant="outlined"
                    size="small"
                    href="https://shell.cloud.google.com/?show=terminal"
                    target="_blank"
                    rel="noopener"
                    startIcon={<CloudIcon sx={{ fontSize: 14 }} />}
                    sx={{ fontSize: '0.68rem', textTransform: 'none', mb: 1 }}
                  >
                    Open Google Cloud Shell (browser)
                  </Button>
                  <TextField
                    fullWidth
                    type="password"
                    label="Access Token"
                    value={tokenInput}
                    onChange={(e) => setTokenInput(e.target.value)}
                    placeholder="ya29..."
                    size="small"
                    sx={{ mb: 1, '& .MuiInputBase-input': { fontSize: '0.75rem' } }}
                    onKeyDown={(e) => e.key === 'Enter' && applyToken()}
                  />
                  <Button
                    fullWidth
                    variant={loginSuccess ? "outlined" : "contained"}
                    onClick={applyToken}
                    disabled={!tokenInput.trim() && !loginSuccess}
                    size="small"
                    startIcon={loginSuccess ? <CheckCircleIcon /> : <LockOpenIcon />}
                    color={loginSuccess ? "success" : "primary"}
                    sx={{ fontSize: '0.72rem', textTransform: 'none' }}
                  >
                    {loginSuccess ? (tokenInput.trim() ? 'Replace Token' : 'Token Set ✓') : 'Use Token'}
                  </Button>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5, fontSize: '0.6rem' }}>
                    Token stays in this browser tab and expires after about 1 hour. All actions run on your own project.
                  </Typography>
                </>
              ) : (
                <>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1, fontSize: '0.65rem' }}>
                    Opens Google sign-in in your browser
                  </Typography>
                  <Button
                    fullWidth
                    variant={loginSuccess ? "outlined" : "contained"}
                    onClick={handleLogin}
                    disabled={loginInProgress}
                    size="small"
                    startIcon={
                      loginInProgress ? <CircularProgress size={14} /> :
                      loginSuccess ? <CheckCircleIcon /> : <LockOpenIcon />
                    }
                    color={loginSuccess ? "success" : "primary"}
                    sx={{ fontSize: '0.72rem', textTransform: 'none' }}
                  >
                    {loginInProgress ? 'Complete in browser...' :
                     loginSuccess ? 'Authenticated ✓' : 'Authenticate with Google'}
                  </Button>
                </>
              )}
              {loginError && (
                <Alert severity="error" sx={{ mt: 1, py: 0.25, '& .MuiAlert-message': { fontSize: '0.7rem' } }}>
                  {loginError}
                </Alert>
              )}
            </Box>

            {/* Step 2: Project + Connect — disabled until Step 1 done */}
            <Box sx={{
              mb: 2, p: 1.5, borderRadius: 1,
              bgcolor: isReady ? '#e6f4ea' : (!loginSuccess ? '#f5f5f5' : '#f8f9fa'),
              border: isReady ? '1px solid #34a853' : '1px solid #e8eaed',
              opacity: loginSuccess ? 1 : 0.5,
              transition: 'all 0.3s',
              pointerEvents: loginSuccess ? 'auto' : 'none',
            }}>
              <Typography variant="caption" sx={{ fontWeight: 600, color: '#3c4043', display: 'block', mb: 0.5 }}>
                Step 2: Connect to Project
              </Typography>
              {!loginSuccess && (
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1, fontSize: '0.65rem' }}>
                  Complete Step 1 first
                </Typography>
              )}
              {loginSuccess && (
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1, fontSize: '0.65rem' }}>
                  Enter your GCP project ID
                </Typography>
              )}
              <TextField
                fullWidth
                label="GCP Project ID"
                value={projectInput}
                onChange={(e) => setProjectInput(e.target.value)}
                placeholder="my-project-123"
                size="small"
                disabled={!loginSuccess}
                sx={{ mb: 1, '& .MuiInputBase-input': { fontSize: '0.8rem' } }}
                onKeyDown={(e) => e.key === 'Enter' && checkAuth()}
              />
              <Button
                fullWidth
                variant={isReady ? "outlined" : "contained"}
                onClick={checkAuth}
                disabled={!projectInput.trim() || authChecking || !loginSuccess}
                size="small"
                startIcon={
                  authChecking ? <CircularProgress size={14} /> :
                  isReady ? <CheckCircleIcon /> : <LinkIcon />
                }
                color={isReady ? "success" : "primary"}
                sx={{ fontSize: '0.72rem', textTransform: 'none' }}
              >
                {authChecking ? 'Checking...' :
                 isReady ? 'Connected ✓' : 'Connect'}
              </Button>
            </Box>

            {/* Errors */}
            {authStatus && !isReady && (
              <Box>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, mb: 1 }}>
                  <Chip
                    icon={authStatus.authenticated ? <CheckCircleIcon /> : <ErrorIcon />}
                    label={authStatus.authenticated ? 'Auth ✓' : 'Not Auth'}
                    color={authStatus.authenticated ? 'success' : 'error'}
                    size="small"
                    sx={{ height: 22, fontSize: '0.65rem', justifyContent: 'flex-start' }}
                  />
                  {authStatus.authenticated && (
                    <Chip
                      icon={authStatus.projectValid ? <CheckCircleIcon /> : <ErrorIcon />}
                      label={authStatus.projectValid ? 'Project ✓' : 'Project ✗'}
                      color={authStatus.projectValid ? 'success' : 'error'}
                      size="small"
                      sx={{ height: 22, fontSize: '0.65rem', justifyContent: 'flex-start' }}
                    />
                  )}
                  {authStatus.projectValid && (
                    <Chip
                      icon={authStatus.computeApiEnabled ? <CheckCircleIcon /> : <ErrorIcon />}
                      label={authStatus.computeApiEnabled ? 'API ✓' : 'API ✗'}
                      color={authStatus.computeApiEnabled ? 'success' : 'error'}
                      size="small"
                      sx={{ height: 22, fontSize: '0.65rem', justifyContent: 'flex-start' }}
                    />
                  )}
                </Box>

                {authStatus.errors?.length > 0 && (
                  <Alert severity="error" sx={{ mb: 1, py: 0.5, '& .MuiAlert-message': { fontSize: '0.7rem' } }}>
                    {authStatus.errors.map((err, i) => (
                      <Typography key={i} variant="caption" sx={{ display: 'block', mb: 0.3 }}>{err}</Typography>
                    ))}
                  </Alert>
                )}

                {authStatus.instructions?.length > 0 && (
                  <Alert severity="info" sx={{ py: 0.5, '& .MuiAlert-message': { fontSize: '0.7rem', width: '100%' } }}>
                    <Typography variant="caption" sx={{ fontWeight: 600 }}>Fix:</Typography>
                    {authStatus.instructions.map((inst, i) => (
                      <Box key={i} sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.3 }}>
                        <code style={{ background: '#f1f3f4', padding: '1px 4px', borderRadius: 3, fontSize: '0.65rem', flex: 1, wordBreak: 'break-all' }}>
                          {inst}
                        </code>
                        <IconButton size="small" onClick={() => copyCmd(inst)} sx={{ p: 0.2 }}>
                          <ContentCopyIcon sx={{ fontSize: 12 }} />
                        </IconButton>
                      </Box>
                    ))}
                  </Alert>
                )}
              </Box>
            )}
          </Box>

          {/* Footer */}
          <Box sx={{ p: 1.5, borderTop: 1, borderColor: 'divider' }}>
            <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem', display: 'block', textAlign: 'center' }}>
              Capacity Radar &mdash; GPU/TPU Capacity Hunting Tool
            </Typography>
          </Box>
        </Drawer>

        {/* Main Content */}
        <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, transition: 'margin 0.3s' }}>
          {/* Tabs */}
          <Box sx={{ bgcolor: '#fff', borderBottom: 1, borderColor: 'divider', px: 3 }}>
            <Tabs
              value={tab}
              onChange={(_, v) => setTab(v)}
              sx={{
                '& .MuiTab-root': { minHeight: 48, py: 0 },
                '& .MuiTabs-indicator': { bgcolor: '#1a73e8' },
              }}
            >
              <Tab icon={<TipsAndUpdatesIcon sx={{ fontSize: 18 }} />} iconPosition="start" label="Capacity Advisory" sx={{ gap: 1 }} />
              <Tab icon={<RocketLaunchIcon sx={{ fontSize: 18 }} />} iconPosition="start" label="Scan & Deploy" sx={{ gap: 1 }} />
            </Tabs>
          </Box>

          {/* Content */}
          <Box sx={{ flex: 1, position: 'relative' }}>
            {!isReady && (
              <Box sx={{
                position: 'absolute', inset: 0, bgcolor: 'rgba(255,255,255,0.8)',
                zIndex: 10, display: 'flex', alignItems: 'center', justifyContent: 'center',
                backdropFilter: 'blur(2px)',
              }}>
                <Paper sx={{ p: 4, textAlign: 'center', maxWidth: 400 }}>
                  <LockOpenIcon sx={{ fontSize: 48, color: '#dadce0', mb: 2 }} />
                  <Typography variant="h6" sx={{ mb: 1, color: '#5f6368' }}>
                    Connect to get started
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                    Authenticate with Google Cloud and connect to your project using the panel on the left.
                  </Typography>
                  {!drawerOpen && (
                    <Button variant="outlined" size="small" onClick={() => setDrawerOpen(true)} startIcon={<MenuIcon />}>
                      Open Auth Panel
                    </Button>
                  )}
                </Paper>
              </Box>
            )}

            <Container maxWidth="xl" sx={{ py: 3 }}>
              <TabPanel value={tab} index={0}>
                <AdvisoryPanel machineTypes={machineTypes} loading={loading} project={project} userToken={userToken} />
              </TabPanel>
              <TabPanel value={tab} index={1}>
                <ScanningPanel machineTypes={machineTypes} loading={loading} project={project} userToken={userToken} />
              </TabPanel>
            </Container>
          </Box>
        </Box>
      </Box>

      {/* Demo Mode Dialog */}
      <Dialog open={demoDialogOpen} onClose={() => setDemoDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1, pb: 1 }}>
          <CloudIcon sx={{ color: '#1a73e8' }} />
          <span>Demo Mode</span>
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2, color: '#5f6368' }}>
            This is a hosted demo of <strong>Capacity Radar</strong>. Authentication, project switching,
            and GPU/TPU deployment are disabled in this version.
          </Typography>

          <Typography variant="body2" sx={{ mb: 0.5, fontWeight: 600, color: '#3c4043' }}>
            Prerequisites
          </Typography>
          <Typography variant="caption" sx={{ display: 'block', mb: 1.5, color: '#5f6368', lineHeight: 1.5 }}>
            Python 3.10+ &bull; Node.js 18+ &amp; npm &bull; Google Cloud SDK (gcloud) &bull; A GCP project with Compute Engine API enabled
          </Typography>

          <Typography variant="body2" sx={{ mb: 1, fontWeight: 600, color: '#3c4043' }}>
            Quick Start
          </Typography>
          <Box sx={{ bgcolor: '#f8f9fa', borderRadius: 1, p: 2, border: '1px solid #e8eaed' }}>
            {[
              { step: '1', label: 'Clone the repo', cmd: `git clone ${repoUrl || 'https://github.com/MG-Cafe/capacity_radar.git'} && cd capacity_radar` },
              { step: '2', label: 'Authenticate', cmd: 'gcloud auth application-default login' },
              { step: '3', label: 'Set project (optional)', cmd: 'gcloud config set project YOUR_PROJECT_ID' },
              { step: '4', label: 'Install backend deps', cmd: 'cd backend && pip install -r requirements.txt' },
              { step: '5', label: 'Build frontend', cmd: 'cd ../frontend && npm install && npm run build' },
              { step: '6', label: 'Run the app', cmd: 'cd ../backend && python main.py' },
            ].map(({ step, label, cmd }) => (
              <Box key={step} sx={{ mb: 1.2 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.3 }}>
                  <Chip label={step} size="small" sx={{ height: 18, minWidth: 18, fontSize: '0.6rem', bgcolor: '#1a73e8', color: '#fff' }} />
                  <Typography variant="caption" sx={{ fontWeight: 600, color: '#3c4043', fontSize: '0.72rem' }}>{label}</Typography>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, ml: 3 }}>
                  <code style={{ flex: 1, fontSize: '0.72rem', background: '#e8eaed', padding: '4px 8px', borderRadius: 4, color: '#3c4043' }}>{cmd}</code>
                  <IconButton size="small" onClick={() => copyCmd(cmd)} sx={{ p: 0.3 }}>
                    <ContentCopyIcon sx={{ fontSize: 13 }} />
                  </IconButton>
                </Box>
              </Box>
            ))}
          </Box>
          <Typography variant="caption" sx={{ display: 'block', mt: 1.5, color: '#5f6368' }}>
            The app will be available at <strong>http://localhost:8000</strong>
          </Typography>
          <Alert severity="info" sx={{ mt: 1.5, py: 0.5 }}>
            <Typography variant="caption">
              The <strong>Capacity Advisory</strong> tab is fully functional in this demo.
              Only deployment (Scan &amp; Deploy) and project configuration are restricted.
            </Typography>
          </Alert>
        </DialogContent>
        <DialogActions>
          {repoUrl && (
            <Button href={repoUrl} target="_blank" size="small" sx={{ textTransform: 'none' }}>
              View on GitHub
            </Button>
          )}
          <Button onClick={() => setDemoDialogOpen(false)} variant="contained" size="small" sx={{ textTransform: 'none' }}>
            Got it
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
