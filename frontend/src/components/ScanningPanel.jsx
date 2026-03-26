import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import {
  Box, Paper, Typography, Grid, TextField, MenuItem, Button,
  Alert, AlertTitle, CircularProgress, Chip, Card, CardContent,
  FormControl, InputLabel, Select, OutlinedInput, Checkbox,
  ListItemText, Divider, Tooltip, IconButton, Collapse,
  Stepper, Step, StepLabel, StepContent, LinearProgress,
  Accordion, AccordionSummary, AccordionDetails, Slider,
} from '@mui/material'
import RocketLaunchIcon from '@mui/icons-material/RocketLaunch'
import AddIcon from '@mui/icons-material/Add'
import DeleteIcon from '@mui/icons-material/Delete'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import StopIcon from '@mui/icons-material/Stop'
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward'
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import SettingsIcon from '@mui/icons-material/Settings'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import ErrorIcon from '@mui/icons-material/Error'
import WarningIcon from '@mui/icons-material/Warning'
import AccessTimeIcon from '@mui/icons-material/AccessTime'
import CancelIcon from '@mui/icons-material/Cancel'
import MemoryIcon from '@mui/icons-material/Memory'
import StorageIcon from '@mui/icons-material/Storage'
import MachineTypeSelector from './MachineTypeSelector'
import CalendarMonthIcon from '@mui/icons-material/CalendarMonth'
import BoltIcon from '@mui/icons-material/Bolt'
import CloudQueueIcon from '@mui/icons-material/CloudQueue'
import LinearScaleIcon from '@mui/icons-material/LinearScale'
import AccountTreeIcon from '@mui/icons-material/AccountTree'
import VpnKeyIcon from '@mui/icons-material/VpnKey'
import SearchIcon from '@mui/icons-material/Search'
import CloudDoneIcon from '@mui/icons-material/CloudDone'
import SyncIcon from '@mui/icons-material/Sync'
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty'
import LabelIcon from '@mui/icons-material/Label'
import VisibilityIcon from '@mui/icons-material/Visibility'
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff'
import { ToggleButton, ToggleButtonGroup, FormControlLabel, Switch } from '@mui/material'


const METHOD_OPTIONS = [
  { value: 'on_demand', label: 'On-Demand Reservation', icon: <StorageIcon sx={{ fontSize: 18 }} />, color: '#1a73e8', desc: 'Reserve capacity at on-demand rates. Pay per second.' },
  { value: 'dws_calendar', label: 'DWS Calendar Mode', icon: <CalendarMonthIcon sx={{ fontSize: 18 }} />, color: '#34a853', desc: 'Book capacity for a specific time window (1–90 days).' },
  { value: 'dws_flex', label: 'DWS Flex Start', icon: <CloudQueueIcon sx={{ fontSize: 18 }} />, color: '#9334e6', desc: 'Queue for capacity. Starts when available (usage max 14 days).' },
  { value: 'spot', label: 'Spot VMs', icon: <BoltIcon sx={{ fontSize: 18 }} />, color: '#f9ab00', desc: 'Spare capacity at discount. Can be preempted anytime.' },
]

const DEFAULT_PRIORITY = {
  method: 'on_demand',
  zones: [],
  max_retries: 5,
  retry_interval: 60,
}

// Strip emojis from backend messages for clean GCP-style display
function stripEmojis(text) {
  if (!text) return ''
  return text
    .replace(/[\u{1F300}-\u{1F9FF}]|[\u{2600}-\u{27BF}]|[\u{FE00}-\u{FE0F}]|[\u{1F000}-\u{1F02F}]|[\u{1F680}-\u{1F6FF}]|[\u{200D}]|[\u{20E3}]|[\u{FE0F}]|[\u{E0020}-\u{E007F}]|[✅❌⚠️🔑📋🔍📌🔄📡⏳🛑⚡🎉🏷️]/gu, '')
    .replace(/^\s+/, '')
}

export default function ScanningPanel({ machineTypes = [], loading: mtLoading, project = '' }) {
  
  const [category, setCategory] = useState('GPU')
  const [chip, setChip] = useState('')
  const [machineType, setMachineType] = useState('')
  const [minVmCount, setMinVmCount] = useState(1)
  const [maxVmCount, setMaxVmCount] = useState(1)
  const [totalHuntingHours, setTotalHuntingHours] = useState(1)
  const [priorities, setPriorities] = useState([{ ...DEFAULT_PRIORITY }])
  const [executionMode, setExecutionMode] = useState('sequential')
  const [showUnsupported, setShowUnsupported] = useState(false)

  // Scanning state
  const [scanning, setScanning] = useState(false)
  const [sessionId, setSessionId] = useState(null)
  const [logs, setLogs] = useState([])
  const [scanStatus, setScanStatus] = useState(null)
  const [progress, setProgress] = useState(0)
  const wsRef = useRef(null)
  const logContainerRef = useRef(null)

  // Machine type info
  const selectedMachineInfo = useMemo(() => {
    return machineTypes.find(mt => mt.machineType === machineType)
  }, [machineType, machineTypes])

  const availableZones = useMemo(() => {
    return selectedMachineInfo?.zones || []
  }, [selectedMachineInfo])

  // Auto-scroll only the log container (not the page)
  useEffect(() => {
    if (logContainerRef.current && logs.length > 0) {
      const container = logContainerRef.current
      // Only auto-scroll if user is near the bottom
      const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100
      if (isNearBottom) {
        requestAnimationFrame(() => {
          container.scrollTop = container.scrollHeight
        })
      }
    }
  }, [logs])

  // Progress tracking
  useEffect(() => {
    if (!scanning) {
      if (scanStatus === 'success') setProgress(100)
      else if (scanStatus === 'failed') setProgress(100)
      return
    }
    // Calculate progress from logs
    const totalZones = availableZones.length || 1
    const totalRetries = priorities.reduce((s, p) => s + p.max_retries, 0) || 1
    const attempts = logs.filter(l => l.type === 'attempt').length
    const maxAttempts = totalZones * totalRetries
    setProgress(Math.min(95, Math.round((attempts / maxAttempts) * 100)))
  }, [logs, scanning, scanStatus, availableZones, priorities])

  // Auto-switch priority methods to supported ones when machine type changes
  useEffect(() => {
    if (!selectedMachineInfo || showUnsupported) return
    const supported = selectedMachineInfo.supported || {}
    const supportedMethods = METHOD_OPTIONS.filter(m => supported[m.value] !== false).map(m => m.value)
    if (supportedMethods.length === 0) return

    setPriorities(prev => {
      let changed = false
      const updated = prev.map(p => {
        if (supported[p.method] === false) {
          changed = true
          return { ...p, method: supportedMethods[0], zones: [] }
        }
        return p
      })
      return changed ? updated : prev
    })
  }, [selectedMachineInfo, showUnsupported])

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) wsRef.current.close()
    }
  }, [])

  // Priority management
  const addPriority = () => setPriorities([...priorities, { ...DEFAULT_PRIORITY }])

  const removePriority = (index) => {
    if (priorities.length <= 1) return
    setPriorities(priorities.filter((_, i) => i !== index))
  }

  const movePriority = (index, direction) => {
    const newIndex = index + direction
    if (newIndex < 0 || newIndex >= priorities.length) return
    const updated = [...priorities]
    const temp = updated[index]
    updated[index] = updated[newIndex]
    updated[newIndex] = temp
    setPriorities(updated)
  }

  const updatePriority = (index, field, value) => {
    const updated = [...priorities]
    updated[index] = { ...updated[index], [field]: value }
    setPriorities(updated)
  }

  // Start scan
  const startScan = useCallback(() => {
    if (!machineType || !project || priorities.length === 0) return

    setScanning(true)
    setScanStatus('running')
    setLogs([])
    setSessionId(null)
    setProgress(0)

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/scan`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      const config = {
        project,
        machineType,
        vmCount: maxVmCount,
        minVmCount,
        maxVmCount,
        totalHuntingHours,
        priorities: priorities.map(p => ({
          method: p.method,
          zones: p.zones.length > 0 ? p.zones : availableZones,
          max_retries: p.max_retries,
          retry_interval: p.retry_interval,
          name_prefix: p.namePrefix || '',
          flex_max_wait_hours: p.flexMaxWaitHours || 168,
          flex_usage_duration_hours: p.flexUsageDurationHours || 24,
          calendar_start_time: p.calendarStartTime || '',
          calendar_end_time: p.calendarEndTime || '',
        })),
        dwsCalendarDurationHours: 24,
        parallel: executionMode === 'parallel',
      }
      ws.send(JSON.stringify({ action: 'scan', config }))
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'session_created') setSessionId(data.sessionId)
        setLogs(prev => [...prev, data])

        if (data.type === 'success') { setScanStatus('success'); setScanning(false) }
        else if (data.type === 'failed') { setScanStatus('failed'); setScanning(false) }
        else if (data.type === 'cancelled') { setScanStatus('cancelled'); setScanning(false) }
        else if (data.type === 'error' && data.status === 'failed') { setScanStatus('failed'); setScanning(false) }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e)
      }
    }

    ws.onerror = () => {
      setLogs(prev => [...prev, {
        type: 'error', message: 'WebSocket connection error. Check backend.',
        timestamp: new Date().toISOString(),
      }])
      setScanStatus('failed')
      setScanning(false)
    }

    ws.onclose = () => {
      setScanning(false)
      setScanStatus(prev => prev === 'running' ? 'cancelled' : prev)
    }
  }, [machineType, project, priorities, minVmCount, maxVmCount, totalHuntingHours, availableZones, executionMode])

  const cancelScan = useCallback(() => {
    if (wsRef.current) {
      if (sessionId && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ action: 'cancel', sessionId }))
      }
      // Also close the WebSocket to force-stop
      setTimeout(() => {
        if (wsRef.current) {
          wsRef.current.close()
          wsRef.current = null
        }
        setScanning(false)
        setScanStatus(prev => (!prev || prev === 'running') ? 'cancelled' : prev)
      }, 1000)
    } else {
      setScanning(false)
      setScanStatus('cancelled')
    }
  }, [sessionId])

  const canStart = machineType && project && priorities.length > 0 && !scanning

  return (
    <Box>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h2" sx={{ mb: 0.5, color: '#202124' }}>Scan & Deploy</Typography>
        <Typography variant="body1" color="text.secondary">
          Scan for available GPU/TPU capacity and automatically deploy reservations or VMs.
        </Typography>
      </Box>

      <Grid container spacing={3}>
        {/* Left: Configuration */}
        <Grid item xs={12} lg={6}>
          <Paper sx={{ p: 3, mb: 3 }}>
            <Typography variant="h4" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
              <SettingsIcon sx={{ color: '#1a73e8', fontSize: 20 }} />
              Scan Configuration
            </Typography>
            <Box sx={{ mb: 2 }}>
              <MachineTypeSelector
                machineTypes={machineTypes} category={category}
                setCategory={(val) => { setCategory(val); setPriorities(priorities.map(p => ({ ...p, zones: [] }))) }}
                chip={chip}
                setChip={(val) => { setChip(val); setPriorities(priorities.map(p => ({ ...p, zones: [] }))) }}
                machineType={machineType}
                setMachineType={(val) => { setMachineType(val); setPriorities(priorities.map(p => ({ ...p, zones: [] }))) }}
                disabled={scanning}
              />
            </Box>
            <Grid container spacing={2}>
              <Grid item xs={6} sm={3}>
                <TextField fullWidth type="number" label="Min VMs / Nodes" value={minVmCount}
                  onChange={(e) => {
                    const val = Math.max(1, parseInt(e.target.value) || 1)
                    setMinVmCount(val)
                    if (val > maxVmCount) setMaxVmCount(val)
                  }}
                  size="small" inputProps={{ min: 1 }} disabled={scanning}
                  helperText="Minimum required"
                />
              </Grid>
              <Grid item xs={6} sm={3}>
                <TextField fullWidth type="number" label="Max VMs / Nodes" value={maxVmCount}
                  onChange={(e) => {
                    const val = Math.max(minVmCount, parseInt(e.target.value) || 1)
                    setMaxVmCount(val)
                  }}
                  size="small" inputProps={{ min: minVmCount }} disabled={scanning}
                  helperText="Ideal target"
                />
              </Grid>
              <Grid item xs={6} sm={3}>
                <TextField fullWidth type="number" label="Total Hunting Time (hrs)" value={totalHuntingHours}
                  onChange={(e) => setTotalHuntingHours(Math.max(0.1, parseFloat(e.target.value) || 1))}
                  size="small" inputProps={{ min: 0.1, step: 0.5 }} disabled={scanning}
                  helperText="Max time to scan"
                />
              </Grid>
            </Grid>
            <Box sx={{ mt: 1, display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <InfoOutlinedIcon sx={{ fontSize: 13, color: '#80868b' }} />
              <Typography variant="caption" sx={{ color: '#80868b', fontSize: '0.68rem' }}>
                Total hunting time is the max wait time for trying all priorities. It excludes resource provisioning time.
                {minVmCount < maxVmCount && ` System will try for ${maxVmCount} VMs first, scaling down to ${minVmCount} if needed.`}
              </Typography>
            </Box>
          </Paper>

          <Paper sx={{ p: 3 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
              <Typography variant="h4" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <RocketLaunchIcon sx={{ color: '#1a73e8', fontSize: 20 }} />
                Scanning Priorities
                <Tooltip title="Define the order in which consumption models are tried.">
                  <InfoOutlinedIcon sx={{ fontSize: 16, color: '#80868b', cursor: 'help' }} />
                </Tooltip>
              </Typography>
              <Button size="small" startIcon={<AddIcon />} onClick={addPriority}
                disabled={scanning || priorities.length >= 4}>
                Add Priority
              </Button>
            </Box>

            {/* Show unsupported toggle */}
            {machineType && (
              <Box sx={{ mb: 1.5, display: 'flex', alignItems: 'center', gap: 1 }}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={showUnsupported}
                      onChange={(e) => setShowUnsupported(e.target.checked)}
                      size="small"
                      disabled={scanning}
                    />
                  }
                  label={
                    <Typography variant="caption" sx={{ color: '#5f6368', fontSize: '0.72rem' }}>
                      {showUnsupported ? 'Showing all methods & zones' : 'Showing only supported methods & zones'}
                    </Typography>
                  }
                />
                <Tooltip title="Enable to see methods and zones that are not officially supported for this chip. Useful if Google adds support later.">
                  <InfoOutlinedIcon sx={{ fontSize: 14, color: '#80868b', cursor: 'help' }} />
                </Tooltip>
              </Box>
            )}

            {priorities.map((priority, index) => {
              const methodInfo = METHOD_OPTIONS.find(m => m.value === priority.method)
              const isSupported = selectedMachineInfo?.supported?.[priority.method] !== false

              return (
                <Card key={index} sx={{ mb: 2, border: `1px solid ${isSupported ? '#dadce0' : '#fce8e6'}`, bgcolor: isSupported ? '#fff' : '#fef7f7' }}>
                  <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
                      <Chip label={`#${index + 1}`} size="small"
                        sx={{ bgcolor: methodInfo?.color || '#1a73e8', color: '#fff', fontWeight: 700, height: 24, width: 36, fontSize: '0.75rem' }} />
                      <Typography variant="h6" sx={{ fontWeight: 500, flex: 1 }}>{methodInfo?.label || 'Priority'}</Typography>
                      {!isSupported && machineType && (
                        <Chip label="Not supported" size="small" color="error" variant="outlined" sx={{ height: 22, fontSize: '0.65rem' }} />
                      )}
                      <IconButton size="small" onClick={() => movePriority(index, -1)} disabled={index === 0 || scanning}>
                        <ArrowUpwardIcon sx={{ fontSize: 16 }} />
                      </IconButton>
                      <IconButton size="small" onClick={() => movePriority(index, 1)} disabled={index === priorities.length - 1 || scanning}>
                        <ArrowDownwardIcon sx={{ fontSize: 16 }} />
                      </IconButton>
                      <IconButton size="small" onClick={() => removePriority(index)} disabled={priorities.length <= 1 || scanning} sx={{ color: '#d93025' }}>
                        <DeleteIcon sx={{ fontSize: 16 }} />
                      </IconButton>
                    </Box>

                    <Grid container spacing={2}>
                      <Grid item xs={12} sm={4}>
                        <TextField fullWidth select label="Method" value={priority.method}
                          onChange={(e) => updatePriority(index, 'method', e.target.value)} size="small" disabled={scanning}>
                          {METHOD_OPTIONS
                            .filter(opt => showUnsupported || !machineType || selectedMachineInfo?.supported?.[opt.value] !== false)
                            .map(opt => {
                              const supported = !machineType || selectedMachineInfo?.supported?.[opt.value] !== false
                              return (
                                <MenuItem key={opt.value} value={opt.value}>
                                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, opacity: supported ? 1 : 0.5 }}>
                                    <Box sx={{ color: opt.color }}>{opt.icon}</Box>
                                    <Box>
                                      <Typography variant="body2" sx={{ fontWeight: 500, lineHeight: 1.2 }}>
                                        {opt.label}
                                        {!supported && <Chip label="unsupported" size="small" sx={{ ml: 0.5, height: 16, fontSize: '0.55rem' }} color="warning" variant="outlined" />}
                                      </Typography>
                                      <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem', whiteSpace: 'normal', lineHeight: 1.3 }}>{opt.desc}</Typography>
                                    </Box>
                                  </Box>
                                </MenuItem>
                              )
                            })}
                        </TextField>
                      </Grid>
                      <Grid item xs={12} sm={4}>
                        <FormControl fullWidth size="small">
                          <InputLabel>Zones</InputLabel>
                          <Select multiple value={priority.zones}
                            onChange={(e) => updatePriority(index, 'zones', e.target.value)}
                            input={<OutlinedInput label="Zones" />}
                            renderValue={(selected) => selected.length === 0 ? 'All available' : `${selected.length} zones`}
                            disabled={!machineType || scanning}>
                            {availableZones.map(zone => (
                              <MenuItem key={zone} value={zone} dense>
                                <Checkbox checked={priority.zones.indexOf(zone) > -1} size="small" />
                                <ListItemText primary={zone} primaryTypographyProps={{ fontSize: '0.8rem' }} />
                              </MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                      </Grid>
                      <Grid item xs={6} sm={2}>
                        <TextField fullWidth type="number" label="Retry Rounds" value={priority.max_retries}
                          onChange={(e) => updatePriority(index, 'max_retries', Math.max(1, Math.min(100, parseInt(e.target.value) || 5)))}
                          size="small" inputProps={{ min: 1, max: 100 }} disabled={scanning}
                          helperText="Each round tries all zones" />
                      </Grid>
                      <Grid item xs={6} sm={2}>
                        <TextField fullWidth type="number" label="Interval (s)" value={priority.retry_interval}
                          onChange={(e) => updatePriority(index, 'retry_interval', Math.max(10, Math.min(3600, parseInt(e.target.value) || 60)))}
                          size="small" inputProps={{ min: 10, max: 3600 }} disabled={scanning} helperText="Wait between rounds" />
                      </Grid>
                    </Grid>

                    {/* Naming convention */}
                    <Box sx={{ mt: 1.5, p: 1.5, bgcolor: '#f8f9fa', borderRadius: 1, border: '1px solid #e8eaed' }}>
                      <Grid container spacing={1.5} alignItems="center">
                        <Grid item xs={12} sm={6}>
                          <TextField fullWidth label="Resource Name Prefix"
                            value={priority.namePrefix || ''}
                            onChange={(e) => updatePriority(index, 'namePrefix', e.target.value.replace(/[^a-z0-9-]/g, ''))}
                            size="small" disabled={scanning}
                            helperText="Custom naming convention (lowercase, hyphens)"
                            placeholder="myteam-prod"
                            InputProps={{ startAdornment: <LabelIcon sx={{ fontSize: 16, mr: 0.5, color: '#80868b' }} /> }}
                          />
                        </Grid>
                        <Grid item xs={12} sm={6}>
                          <Typography variant="caption" color="text.secondary">
                            Preview: <code style={{ fontSize: '0.7rem', background: '#e8eaed', padding: '2px 6px', borderRadius: 3 }}>
                              {priority.namePrefix ? `${priority.namePrefix}-` : 'gpu-radar-'}{priority.method === 'spot' ? 'spot' : priority.method === 'dws_calendar' ? 'cal' : priority.method === 'dws_flex' ? 'flex' : 'od'}-xxxxxxxx-zone
                            </code>
                          </Typography>
                        </Grid>
                      </Grid>
                    </Box>

                    {/* Calendar settings */}
                    {priority.method === 'dws_calendar' && (
                      <Box sx={{ mt: 1.5, p: 1.5, bgcolor: '#e8f5e9', borderRadius: 1, border: '1px solid #c8e6c9' }}>
                        <Typography variant="caption" sx={{ fontWeight: 600, color: '#2e7d32', display: 'flex', alignItems: 'center', gap: 0.5, mb: 1 }}>
                          <CalendarMonthIcon sx={{ fontSize: 14 }} /> Calendar Mode Settings
                        </Typography>
                        <Grid container spacing={1.5}>
                          <Grid item xs={6}>
                            <TextField fullWidth type="datetime-local" label="Start Time"
                              value={priority.calendarStartTime || ''}
                              onChange={(e) => updatePriority(index, 'calendarStartTime', e.target.value)}
                              size="small" disabled={scanning} InputLabelProps={{ shrink: true }}
                              helperText="When reservation begins" />
                          </Grid>
                          <Grid item xs={6}>
                            <TextField fullWidth type="datetime-local" label="End Time"
                              value={priority.calendarEndTime || ''}
                              onChange={(e) => updatePriority(index, 'calendarEndTime', e.target.value)}
                              size="small" disabled={scanning} InputLabelProps={{ shrink: true }}
                              helperText="When reservation ends" />
                          </Grid>
                        </Grid>
                      </Box>
                    )}

                    {priority.method === 'dws_flex' && (
                      <Box sx={{ mt: 1.5, p: 1.5, bgcolor: '#f3e5f5', borderRadius: 1, border: '1px solid #ce93d8' }}>
                        <Typography variant="caption" sx={{ fontWeight: 600, color: '#7b1fa2', display: 'flex', alignItems: 'center', gap: 0.5, mb: 1 }}>
                          <HourglassEmptyIcon sx={{ fontSize: 14 }} /> Flex Start Settings
                        </Typography>
                        <Grid container spacing={1.5}>
                          <Grid item xs={6}>
                            <TextField fullWidth type="number" label="Max Wait for Capacity (hrs)"
                              value={priority.flexMaxWaitHours || 168}
                              onChange={(e) => updatePriority(index, 'flexMaxWaitHours', Math.max(1, Math.min(168, parseInt(e.target.value) || 168)))}
                              size="small" inputProps={{ min: 1, max: 168 }} disabled={scanning}
                              helperText="How long to wait for GPUs (max 7d)" />
                          </Grid>
                          <Grid item xs={6}>
                            <TextField fullWidth type="number" label="Usage Duration (hrs)"
                              value={priority.flexUsageDurationHours || 24}
                              onChange={(e) => updatePriority(index, 'flexUsageDurationHours', Math.max(1, Math.min(720, parseInt(e.target.value) || 24)))}
                              size="small" inputProps={{ min: 1, max: 720 }} disabled={scanning}
                              helperText="How long you need the GPUs" />
                          </Grid>
                        </Grid>
                      </Box>
                    )}
                  </CardContent>
                </Card>
              )
            })}

            {/* Priority Time Allocation */}
            {priorities.length > 0 && (
              <Box sx={{ mt: 1, mb: 2, p: 1.5, bgcolor: '#e8f0fe', borderRadius: 1, border: '1px solid #d2e3fc' }}>
                <Typography variant="caption" sx={{ fontWeight: 600, color: '#1a73e8', display: 'flex', alignItems: 'center', gap: 0.5, mb: 1 }}>
                  <AccessTimeIcon sx={{ fontSize: 14 }} /> Time Allocation per Priority
                </Typography>
                {(() => {
                  const totalHuntingSecs = totalHuntingHours * 3600
                  const allocations = priorities.map((p, i) => {
                    const secs = p.max_retries * p.retry_interval
                    const pct = totalHuntingSecs > 0 ? Math.round((secs / totalHuntingSecs) * 100) : 0
                    const hrs = (secs / 3600).toFixed(1)
                    const methodInfo = METHOD_OPTIONS.find(m => m.value === p.method)
                    return { secs, pct, hrs, label: methodInfo?.label || p.method, color: methodInfo?.color || '#666', index: i }
                  })
                  const totalAllocSecs = allocations.reduce((s, a) => s + a.secs, 0)
                  const totalAllocHrs = (totalAllocSecs / 3600).toFixed(1)
                  const overUnder = totalAllocSecs - totalHuntingSecs
                  const isOver = overUnder > 60
                  const isUnder = overUnder < -60

                  return (
                    <>
                      {/* Stacked bar */}
                      <Box sx={{ display: 'flex', height: 16, borderRadius: 2, overflow: 'hidden', mb: 1, bgcolor: '#e8eaed' }}>
                        {allocations.map((a, i) => (
                          <Tooltip key={i} title={`#${a.index + 1} ${a.label}: ${a.hrs}h (${a.pct}%)`}>
                            <Box sx={{ width: `${Math.max(a.pct, 2)}%`, bgcolor: a.color, opacity: 0.85, transition: 'width 0.3s' }} />
                          </Tooltip>
                        ))}
                      </Box>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 0.5 }}>
                        {allocations.map((a, i) => (
                          <Chip key={i} size="small"
                            label={`#${a.index + 1} ${a.label}: ${a.hrs}h (${a.pct}%)`}
                            sx={{ height: 20, fontSize: '0.62rem', bgcolor: a.color + '22', color: a.color, fontWeight: 600, border: `1px solid ${a.color}44` }}
                          />
                        ))}
                      </Box>
                      <Typography variant="caption" sx={{ color: (isOver || isUnder) ? '#d93025' : '#5f6368', fontSize: '0.66rem' }}>
                        Total allocated: {totalAllocHrs}h / {totalHuntingHours}h
                        {isOver && ' ⚠ Exceeds total hunting time'}
                        {isUnder && ' — unused time remaining'}
                        {!isOver && !isUnder && ' ✓'}
                      </Typography>
                    </>
                  )
                })()}
              </Box>
            )}

            {/* Execution Mode */}
            <Box sx={{ mt: 2, mb: 2, p: 2, bgcolor: '#f8f9fa', borderRadius: 1, border: '1px solid #e8eaed' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                <Typography variant="body2" sx={{ fontWeight: 500, color: '#3c4043' }}>Execution Mode:</Typography>
                <ToggleButtonGroup value={executionMode} exclusive
                  onChange={(_, val) => { if (val) setExecutionMode(val) }}
                  size="small" disabled={scanning}
                  sx={{ '& .MuiToggleButton-root': { py: 0.5, px: 2 } }}>
                  <ToggleButton value="sequential" sx={{ textTransform: 'none', gap: 0.5, fontWeight: 500, fontSize: '0.8rem' }}>
                    <LinearScaleIcon sx={{ fontSize: 16 }} /> Sequential
                  </ToggleButton>
                  <ToggleButton value="parallel" sx={{ textTransform: 'none', gap: 0.5, fontWeight: 500, fontSize: '0.8rem' }}>
                    <AccountTreeIcon sx={{ fontSize: 16 }} /> Parallel
                  </ToggleButton>
                </ToggleButtonGroup>
              </Box>
              <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                {executionMode === 'sequential'
                  ? 'Priorities run one after another in the order defined above.'
                  : 'All priorities run at the same time — first one to get capacity wins.'}
              </Typography>
            </Box>

            <Box sx={{ display: 'flex', gap: 1.5 }}>
              <Button variant="contained" size="large" onClick={startScan} disabled={!canStart}
                startIcon={<PlayArrowIcon />}
                sx={{ bgcolor: '#1a73e8', px: 4, '&:hover': { bgcolor: '#1557b0' } }}>
                Start Scan & Deploy
              </Button>
            </Box>
          </Paper>
        </Grid>

        {/* Right: Progress */}
        <Grid item xs={12} lg={6}>
          <Paper sx={{ p: 3, height: '100%', display: 'flex', flexDirection: 'column' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <AccessTimeIcon sx={{ color: '#1a73e8', fontSize: 22 }} />
              <Typography variant="h4">Scanning Progress</Typography>
              {scanning && <CircularProgress size={18} sx={{ ml: 1 }} />}
              {scanStatus && <StatusChip status={scanStatus} />}
              {sessionId && (
                <Chip label={`Session: ${sessionId.substring(0, 8)}...`}
                  size="small" variant="outlined"
                  sx={{ ml: 'auto', height: 22, fontSize: '0.65rem' }} />
              )}
            </Box>

            {/* Progress bar + Cancel */}
            <Box sx={{ mb: 1.5 }}>
              <LinearProgress
                variant={scanning && progress < 5 ? 'indeterminate' : 'determinate'}
                value={progress}
                sx={{
                  height: 6, borderRadius: 3,
                  bgcolor: '#e8eaed',
                  '& .MuiLinearProgress-bar': {
                    borderRadius: 3,
                    bgcolor: scanStatus === 'success' ? '#1e8e3e' : scanStatus === 'failed' ? '#d93025' : '#1a73e8',
                  }
                }}
              />
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 0.5 }}>
                {scanning ? (
                  <Button size="small" onClick={cancelScan} startIcon={<StopIcon sx={{ fontSize: 14 }} />}
                    color="error" variant="outlined"
                    sx={{ fontSize: '0.72rem', py: 0.25, px: 1.5, textTransform: 'none' }}>
                    Cancel Scan
                  </Button>
                ) : <Box />}
                {(scanning || scanStatus) && (
                  <Typography variant="caption" color="text.secondary">
                    {scanStatus === 'success' ? 'Completed' : scanStatus === 'failed' ? 'Failed' : `${progress}%`}
                  </Typography>
                )}
              </Box>
            </Box>

            {/* Log entries */}
            <Box
              ref={logContainerRef}
              sx={{
                flex: 1, minHeight: 400, maxHeight: 'calc(100vh - 420px)',
                overflowY: 'auto', bgcolor: '#f8f9fa', borderRadius: 1,
                border: '1px solid #dadce0', p: 1.5,
              }}
            >
              {logs.length === 0 ? (
                <Box sx={{ textAlign: 'center', py: 8, color: '#80868b' }}>
                  <RocketLaunchIcon sx={{ fontSize: 48, mb: 1, opacity: 0.3 }} />
                  <Typography variant="body2">
                    Configure your scanning priorities and click "Start Scan" to begin.
                  </Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
                    Progress will appear here in real-time.
                  </Typography>
                </Box>
              ) : (
                logs.map((log, idx) => <LogEntry key={idx} log={log} />)
              )}
            </Box>

            {scanStatus === 'success' && (
              <Alert severity="success" icon={<CloudDoneIcon />} sx={{ mt: 2 }}>
                <AlertTitle>Deployed Successfully</AlertTitle>
                Capacity has been secured and verified. Check the logs above for resource details.
              </Alert>
            )}
            {scanStatus === 'failed' && (
              <Alert severity="error" sx={{ mt: 2 }}>
                <AlertTitle>Deployment Failed</AlertTitle>
                All priorities exhausted. Consider different zones, machine types, or increased retries.
              </Alert>
            )}
            {scanStatus === 'cancelled' && (
              <Alert severity="warning" sx={{ mt: 2 }}>
                <AlertTitle>Scan Cancelled</AlertTitle>
                The scanning session was cancelled. Check for partially created resources.
              </Alert>
            )}
          </Paper>
        </Grid>
      </Grid>
    </Box>
  )
}

function LogEntry({ log }) {
  const getIcon = (type) => {
    switch (type) {
      case 'start': return <RocketLaunchIcon sx={{ fontSize: 14, color: '#1a73e8' }} />
      case 'success': return <CheckCircleIcon sx={{ fontSize: 14, color: '#1e8e3e' }} />
      case 'error': case 'failed': return <ErrorIcon sx={{ fontSize: 14, color: '#d93025' }} />
      case 'warning': return <WarningIcon sx={{ fontSize: 14, color: '#e37400' }} />
      case 'priority_start': return <RocketLaunchIcon sx={{ fontSize: 14, color: '#9334e6' }} />
      case 'priority_exhausted': return <ErrorIcon sx={{ fontSize: 14, color: '#d93025' }} />
      case 'attempt': return <SyncIcon sx={{ fontSize: 14, color: '#1a73e8' }} />
      case 'action': return <SettingsIcon sx={{ fontSize: 14, color: '#5f6368' }} />
      case 'waiting': return <HourglassEmptyIcon sx={{ fontSize: 14, color: '#80868b' }} />
      case 'cancelled': return <CancelIcon sx={{ fontSize: 14, color: '#e37400' }} />
      case 'info': return <InfoOutlinedIcon sx={{ fontSize: 14, color: '#1a73e8' }} />
      default: return <InfoOutlinedIcon sx={{ fontSize: 14, color: '#5f6368' }} />
    }
  }

  const getBgColor = (type) => {
    switch (type) {
      case 'success': return '#e6f4ea'
      case 'error': case 'failed': return '#fce8e6'
      case 'warning': return '#fef7e0'
      case 'priority_start': return '#f3e8fd'
      case 'priority_exhausted': return '#fce8e6'
      case 'cancelled': return '#fef7e0'
      default: return 'transparent'
    }
  }

  const timestamp = log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : ''
  const cleanMessage = stripEmojis(log.message)

  // Render demo_notice as a structured card
  if (log.type === 'demo_notice' && log.details) {
    return (
      <Box sx={{ my: 1, p: 1.5, borderRadius: 1, bgcolor: '#e8f0fe', border: '1px solid #d2e3fc' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 1 }}>
          <CloudQueueIcon sx={{ fontSize: 16, color: '#1a73e8' }} />
          <Typography variant="body2" sx={{ fontWeight: 600, color: '#1a73e8', fontSize: '0.82rem' }}>
            {cleanMessage}
          </Typography>
        </Box>
        <Typography variant="caption" sx={{ display: 'block', color: '#5f6368', mb: 1, lineHeight: 1.4 }}>
          {log.details.description}
        </Typography>
        <Typography variant="caption" sx={{ display: 'block', fontWeight: 600, color: '#3c4043', mb: 0.5 }}>
          Run locally with full features:
        </Typography>
        {log.details.steps?.map((step, i) => (
          <Box key={i} sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.3 }}>
            <Typography variant="caption" sx={{ color: '#1a73e8', fontWeight: 700, fontSize: '0.65rem', width: 14 }}>{i + 1}.</Typography>
            <code style={{ fontSize: '0.72rem', background: '#fff', padding: '2px 6px', borderRadius: 3, flex: 1, color: '#3c4043' }}>{step}</code>
          </Box>
        ))}
        {log.details.note && (
          <Typography variant="caption" sx={{ display: 'block', mt: 1, color: '#137333', fontWeight: 500, fontSize: '0.7rem' }}>
            ✓ {log.details.note}
          </Typography>
        )}
      </Box>
    )
  }

  return (
    <Box sx={{
      display: 'flex', alignItems: 'flex-start', gap: 1,
      py: 0.5, px: 1, borderRadius: 0.5,
      bgcolor: getBgColor(log.type), mb: 0.5,
      '&:hover': { bgcolor: log.type === 'success' || log.type === 'error' || log.type === 'failed' ? undefined : '#e8eaed' },
    }}>
      <Box sx={{ mt: 0.25, flexShrink: 0 }}>{getIcon(log.type)}</Box>
      <Typography variant="body2" sx={{
        flex: 1, fontFamily: '"Roboto", sans-serif', fontSize: '0.8rem',
        lineHeight: 1.5, wordBreak: 'break-word',
        fontWeight: (log.type === 'success' || log.type === 'priority_start') ? 500 : 400,
      }}>
        {cleanMessage}
      </Typography>
      <Typography variant="caption" sx={{
        color: '#80868b', fontSize: '0.65rem', flexShrink: 0,
        mt: 0.25, fontFamily: '"Roboto Mono", monospace',
      }}>
        {timestamp}
      </Typography>
    </Box>
  )
}

function StatusChip({ status }) {
  switch (status) {
    case 'running':
      return <Chip label="Running" size="small" color="primary" sx={{ height: 22, fontSize: '0.7rem' }} />
    case 'success':
      return <Chip icon={<CheckCircleIcon />} label="Success" size="small" color="success" sx={{ height: 22, fontSize: '0.7rem' }} />
    case 'failed':
      return <Chip icon={<ErrorIcon />} label="Failed" size="small" color="error" sx={{ height: 22, fontSize: '0.7rem' }} />
    case 'cancelled':
      return <Chip icon={<CancelIcon />} label="Cancelled" size="small" color="warning" sx={{ height: 22, fontSize: '0.7rem' }} />
    default: return null
  }
}
