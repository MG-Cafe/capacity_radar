
import React, { useState, useMemo } from 'react'
import {
  Box, Paper, Typography, Grid, TextField, MenuItem, Button,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Alert, AlertTitle, CircularProgress, Chip, Card, CardContent,
  FormControl, InputLabel, Select, OutlinedInput, Checkbox,
  ListItemText, Divider, Tooltip, IconButton, Collapse,
} from '@mui/material'
import SearchIcon from '@mui/icons-material/Search'
import CalendarMonthIcon from '@mui/icons-material/CalendarMonth'
import BoltIcon from '@mui/icons-material/Bolt'
import MachineTypeSelector from './MachineTypeSelector'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import ExpandLessIcon from '@mui/icons-material/ExpandLess'
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline'

export default function AdvisoryPanel({ machineTypes = [], loading: mtLoading, project = '' }) {
  // Shared config
  const [category, setCategory] = useState('GPU')
  const [chip, setChip] = useState('')
  const [machineType, setMachineType] = useState('')
  const [selectedZones, setSelectedZones] = useState([])

  // Calendar-specific params
  const [vmCount, setVmCount] = useState(1)
  const [durationMinDays, setDurationMinDays] = useState(1)
  const [durationMaxDays, setDurationMaxDays] = useState(7)
  const [startFrom, setStartFrom] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() + 1)
    return d.toISOString().split('T')[0]
  })
  const [startTo, setStartTo] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() + 14)
    return d.toISOString().split('T')[0]
  })

  // Results state
  const [calendarResults, setCalendarResults] = useState(null)
  const [spotResults, setSpotResults] = useState(null)
  const [calendarLoading, setCalendarLoading] = useState(false)
  const [spotLoading, setSpotLoading] = useState(false)
  const [calendarError, setCalendarError] = useState(null)
  const [spotError, setSpotError] = useState(null)
  const [showCalendarErrors, setShowCalendarErrors] = useState(false)
  const [showSpotErrors, setShowSpotErrors] = useState(false)

  const selectedMachineInfo = useMemo(() => {
    return machineTypes.find(mt => mt.machineType === machineType)
  }, [machineType, machineTypes])

  const availableZones = useMemo(() => selectedMachineInfo?.zones || [], [selectedMachineInfo])

  const handleZoneChange = (event) => {
    setSelectedZones(typeof event.target.value === 'string' ? event.target.value.split(',') : event.target.value)
  }

  const getZonesAndRegions = () => {
    const zones = selectedZones.length > 0 ? selectedZones : availableZones
    const regions = [...new Set(zones.map(z => z.split('-').slice(0, -1).join('-')))]
    return { zones, regions }
  }

  const queryCalendarAdvisory = async () => {
    setCalendarLoading(true)
    setCalendarError(null)
    setCalendarResults(null)
    try {
      const { zones, regions } = getZonesAndRegions()
      const resp = await fetch('/api/advisory/calendar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project, machineType, vmCount,
          durationMinDays, durationMaxDays, startFrom, startTo,
          regions, zones,
        }),
      })
      if (!resp.ok) {
        const err = await resp.json()
        throw new Error(err.detail || 'Failed to query calendar advisory')
      }
      setCalendarResults(await resp.json())
    } catch (e) {
      setCalendarError(e.message)
    } finally {
      setCalendarLoading(false)
    }
  }

  const querySpotAdvisory = async () => {
    setSpotLoading(true)
    setSpotError(null)
    setSpotResults(null)
    try {
      const { zones, regions } = getZonesAndRegions()
      const resp = await fetch('/api/advisory/spot', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project, machineType, regions, zones }),
      })
      if (!resp.ok) {
        const err = await resp.json()
        throw new Error(err.detail || 'Failed to query spot advisory')
      }
      setSpotResults(await resp.json())
    } catch (e) {
      setSpotError(e.message)
    } finally {
      setSpotLoading(false)
    }
  }

  const supportsCalendar = selectedMachineInfo?.supported?.dws_calendar
  const canQuery = machineType && project

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="h2" sx={{ mb: 0.5, color: '#202124' }}>
          Capacity Advisory
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Check GPU availability using DWS Calendar Mode Advisory and Spot VM Advisory APIs.
        </Typography>
      </Box>

      {/* Shared: Machine Type + Zones */}
      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h4" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
          <SearchIcon sx={{ color: '#1a73e8', fontSize: 20 }} />
          Select Resource
        </Typography>

        <Box sx={{ mb: 2.5 }}>
          <MachineTypeSelector
            machineTypes={machineTypes}
            category={category}
            setCategory={(val) => { setCategory(val); setSelectedZones([]) }}
            chip={chip}
            setChip={(val) => { setChip(val); setSelectedZones([]) }}
            machineType={machineType}
            setMachineType={(val) => { setMachineType(val); setSelectedZones([]) }}
          />
        </Box>

        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} md={5}>
            <FormControl fullWidth size="small">
              <InputLabel>Zones (optional filter)</InputLabel>
              <Select
                multiple
                value={selectedZones}
                onChange={handleZoneChange}
                input={<OutlinedInput label="Zones (optional filter)" />}
                renderValue={(selected) => selected.length === 0 ? 'All zones' : `${selected.length} zones selected`}
                disabled={!machineType}
              >
                {availableZones.map(zone => (
                  <MenuItem key={zone} value={zone}>
                    <Checkbox checked={selectedZones.indexOf(zone) > -1} size="small" />
                    <ListItemText primary={zone} primaryTypographyProps={{ fontSize: '0.8rem' }} />
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          {selectedMachineInfo && (
            <Grid item xs={12} md={7}>
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
                <Typography variant="body2" color="text.secondary" sx={{ mr: 0.5 }}>Supported:</Typography>
                {Object.entries(selectedMachineInfo.supported).map(([key, supported]) => {
                  const labels = { on_demand: 'On-Demand', spot: 'Spot', dws_calendar: 'DWS Calendar', dws_flex: 'DWS Flex' }
                  return (
                    <Chip key={key} label={labels[key]} size="small"
                      color={supported ? 'success' : 'default'}
                      variant={supported ? 'filled' : 'outlined'}
                      sx={{ height: 22, fontSize: '0.65rem', ...(supported ? {} : { opacity: 0.4, textDecoration: 'line-through' }) }}
                    />
                  )
                })}
                <Typography variant="body2" color="text.secondary" sx={{ ml: 0.5 }}>
                  | {availableZones.length} zones
                </Typography>
              </Box>
            </Grid>
          )}
        </Grid>
      </Paper>

      {/* Two advisory sections side by side */}
      <Grid container spacing={3}>
        {/* Calendar Advisory */}
        <Grid item xs={12} lg={6}>
          <Paper sx={{ p: 3, height: '100%' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
              <CalendarMonthIcon sx={{ color: '#1a73e8', fontSize: 22 }} />
              <Typography variant="h4">DWS Calendar Advisory</Typography>
              <Tooltip title="Shows recommended zones and time windows for DWS Calendar mode reservations. Supported for A3, A4, and TPU families.">
                <InfoOutlinedIcon sx={{ fontSize: 16, color: '#80868b', cursor: 'help' }} />
              </Tooltip>
              {calendarLoading && <CircularProgress size={18} sx={{ ml: 'auto' }} />}
            </Box>

            {!selectedMachineInfo?.supported?.dws_calendar && machineType && (
              <Alert severity="info" sx={{ mb: 2 }}>
                DWS Calendar mode is not supported for {machineType}. Only available for A4, A3, and TPU types.
              </Alert>
            )}

            {/* Calendar-specific inputs */}
            {(supportsCalendar || !machineType) && (
              <Box sx={{ bgcolor: '#e8f0fe', borderRadius: 2, p: 2, mb: 2 }}>
                <Grid container spacing={1.5}>
                  <Grid item xs={4}>
                    <TextField fullWidth type="number" label="VM Count" value={vmCount}
                      onChange={(e) => setVmCount(Math.max(1, parseInt(e.target.value) || 1))}
                      size="small" inputProps={{ min: 1 }} />
                  </Grid>
                  <Grid item xs={4}>
                    <TextField fullWidth type="number" label="Min (days)" value={durationMinDays}
                      onChange={(e) => setDurationMinDays(Math.max(1, parseInt(e.target.value) || 1))}
                      size="small" inputProps={{ min: 1, max: 90 }} />
                  </Grid>
                  <Grid item xs={4}>
                    <TextField fullWidth type="number" label="Max (days)" value={durationMaxDays}
                      onChange={(e) => setDurationMaxDays(Math.max(1, parseInt(e.target.value) || 7))}
                      size="small" inputProps={{ min: 1, max: 90 }} />
                  </Grid>
                  <Grid item xs={6}>
                    <TextField fullWidth type="date" label="Start from" value={startFrom}
                      onChange={(e) => setStartFrom(e.target.value)} size="small"
                      InputLabelProps={{ shrink: true }} helperText="Earliest start" />
                  </Grid>
                  <Grid item xs={6}>
                    <TextField fullWidth type="date" label="Start to" value={startTo}
                      onChange={(e) => setStartTo(e.target.value)} size="small"
                      InputLabelProps={{ shrink: true }} helperText="Latest start" />
                  </Grid>
                </Grid>
                <Button
                  fullWidth variant="contained" sx={{ mt: 1.5 }}
                  onClick={queryCalendarAdvisory}
                  disabled={!canQuery || calendarLoading || !supportsCalendar}
                  startIcon={calendarLoading ? <CircularProgress size={16} /> : <CalendarMonthIcon />}
                >
                  Query Calendar Advisory
                </Button>
              </Box>
            )}

            {calendarError && (
              <Alert severity="error" sx={{ mb: 2 }}>
                <AlertTitle>Calendar Advisory Error</AlertTitle>
                {calendarError}
              </Alert>
            )}

            {calendarResults && (
              <>
                {calendarResults.tpuInfo && (
                  <Alert severity="info" sx={{ mb: 2, '& .MuiAlert-message': { fontSize: '0.8rem', width: '100%' } }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5 }}>
                      {calendarResults.tpuInfo.name} — {calendarResults.tpuInfo.machineType}
                    </Typography>
                    <Typography variant="body2" sx={{ mb: 1 }}>{calendarResults.message}</Typography>
                    <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 1 }}>
                      {calendarResults.tpuInfo.specs?.chips && <Chip label={`${calendarResults.tpuInfo.specs.chips} chips`} size="small" sx={{ height: 22, fontSize: '0.65rem' }} />}
                      {calendarResults.tpuInfo.specs?.vcpus && <Chip label={`${calendarResults.tpuInfo.specs.vcpus} vCPUs`} size="small" sx={{ height: 22, fontSize: '0.65rem' }} />}
                      {calendarResults.tpuInfo.specs?.memory_gb && <Chip label={`${calendarResults.tpuInfo.specs.memory_gb} GB RAM`} size="small" sx={{ height: 22, fontSize: '0.65rem' }} />}
                      {calendarResults.tpuInfo.specs?.hbm_gb && <Chip label={`${calendarResults.tpuInfo.specs.hbm_gb} GB HBM`} size="small" sx={{ height: 22, fontSize: '0.65rem' }} />}
                    </Box>
                    <Typography variant="caption" color="text.secondary">
                      <strong>Zones:</strong> {calendarResults.tpuInfo.zones?.join(', ')}
                    </Typography>
                    {calendarResults.tpuInfo.topologies?.length > 0 && (
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                        <strong>Topologies:</strong> {calendarResults.tpuInfo.topologies.join(', ')}
                      </Typography>
                    )}
                    <Box sx={{ display: 'flex', gap: 0.5, mt: 1, flexWrap: 'wrap' }}>
                      <Chip label="On-Demand" size="small" color={calendarResults.tpuInfo.supported?.on_demand ? 'success' : 'default'} variant="outlined" sx={{ height: 20, fontSize: '0.6rem' }} />
                      <Chip label="Spot" size="small" color={calendarResults.tpuInfo.supported?.spot ? 'success' : 'default'} variant="outlined" sx={{ height: 20, fontSize: '0.6rem' }} />
                      <Chip label="DWS Calendar" size="small" color={calendarResults.tpuInfo.supported?.dws_calendar ? 'success' : 'default'} variant="outlined" sx={{ height: 20, fontSize: '0.6rem' }} />
                      <Chip label="DWS Flex" size="small" color={calendarResults.tpuInfo.supported?.dws_flex ? 'success' : 'default'} variant="outlined" sx={{ height: 20, fontSize: '0.6rem' }} />
                    </Box>
                  </Alert>
                )}
                {calendarResults.recommendations.length > 0 ? (
                  <TableContainer>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>Zone</TableCell>
                          <TableCell>Status</TableCell>
                          <TableCell>Details</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {calendarResults.recommendations
                          .sort((a, b) => (a.status === 'RECOMMENDED' ? -1 : 1))
                          .map((rec, idx) => (
                          <TableRow key={idx} hover sx={rec.status === 'RECOMMENDED' ? { bgcolor: '#e6f4ea' } : {}}>
                            <TableCell sx={{ fontWeight: 500 }}>{rec.zone}</TableCell>
                            <TableCell>
                              <Chip label={rec.status || 'UNKNOWN'} size="small"
                                color={rec.status === 'RECOMMENDED' ? 'success' : rec.status === 'NO_CAPACITY' ? 'error' : 'default'}
                                sx={{ height: 22, fontSize: '0.65rem' }} />
                            </TableCell>
                            <TableCell sx={{ fontSize: '0.75rem', color: '#5f6368' }}>
                              {rec.details || (rec.status === 'RECOMMENDED' ? '✅ Capacity available' : '—')}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                ) : (
                  <Alert severity="warning">No calendar advisory recommendations found.</Alert>
                )}
                {calendarResults.errors?.length > 0 && (
                  <Box sx={{ mt: 2 }}>
                    <Button size="small" onClick={() => setShowCalendarErrors(!showCalendarErrors)}
                      endIcon={showCalendarErrors ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                      sx={{ color: '#d93025', fontSize: '0.75rem' }}>
                      {calendarResults.errors.length} zone error(s)
                    </Button>
                    <Collapse in={showCalendarErrors}>
                      <Box sx={{ mt: 1 }}>
                        {calendarResults.errors.map((err, idx) => (
                          <Alert key={idx} severity="warning" sx={{ mb: 0.5, py: 0, '& .MuiAlert-message': { fontSize: '0.75rem' } }}>{err}</Alert>
                        ))}
                      </Box>
                    </Collapse>
                  </Box>
                )}
              </>
            )}

            {!calendarResults && !calendarLoading && !calendarError && !machineType && (
              <Box sx={{ textAlign: 'center', py: 3, color: '#80868b' }}>
                <CalendarMonthIcon sx={{ fontSize: 40, mb: 1, opacity: 0.3 }} />
                <Typography variant="body2">Select a machine type above first</Typography>
              </Box>
            )}
          </Paper>
        </Grid>

        {/* Spot Advisory */}
        <Grid item xs={12} lg={6}>
          <Paper sx={{ p: 3, height: '100%' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
              <BoltIcon sx={{ color: '#f9ab00', fontSize: 22 }} />
              <Typography variant="h4">Spot VM Advisory</Typography>
              <Tooltip title="This API is currently in Preview. Your project may need whitelisting." arrow>
                <Chip label="Preview" size="small" sx={{ bgcolor: '#fce8e6', color: '#d93025', height: 20, fontSize: '0.65rem', cursor: 'help' }} />
              </Tooltip>
              <Tooltip title="Shows spot VM availability and preemption risk by zone. Works for all VM types.">
                <InfoOutlinedIcon sx={{ fontSize: 16, color: '#80868b', cursor: 'help' }} />
              </Tooltip>
              {spotLoading && <CircularProgress size={18} sx={{ ml: 'auto' }} />}
            </Box>

            {/* Spot query - no extra inputs needed, just query button */}
            <Box sx={{ bgcolor: '#fef7e0', borderRadius: 2, p: 2, mb: 2 }}>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                Spot Advisory requires no additional parameters — it checks availability and preemption risk for the selected machine type across all selected zones.
              </Typography>
              <Button
                fullWidth variant="contained" color="warning"
                onClick={querySpotAdvisory}
                disabled={!canQuery || spotLoading}
                startIcon={spotLoading ? <CircularProgress size={16} /> : <BoltIcon />}
                sx={{ bgcolor: '#f9ab00', '&:hover': { bgcolor: '#e69500' } }}
              >
                Query Spot Advisory
              </Button>
            </Box>

            {spotError && (
              <Alert severity="error" sx={{ mb: 2 }}>
                <AlertTitle>Spot Advisory Error</AlertTitle>
                {spotError}
              </Alert>
            )}

            {spotResults && (
              <>
                {spotResults.tpuInfo && (
                  <Alert severity="info" sx={{ mb: 2, '& .MuiAlert-message': { fontSize: '0.8rem', width: '100%' } }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5 }}>
                      {spotResults.tpuInfo.name} — {spotResults.tpuInfo.machineType}
                    </Typography>
                    <Typography variant="body2" sx={{ mb: 1 }}>{spotResults.message}</Typography>
                    <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                      {spotResults.tpuInfo.specs?.chips && <Chip label={`${spotResults.tpuInfo.specs.chips} chips`} size="small" sx={{ height: 22, fontSize: '0.65rem' }} />}
                      {spotResults.tpuInfo.specs?.vcpus && <Chip label={`${spotResults.tpuInfo.specs.vcpus} vCPUs`} size="small" sx={{ height: 22, fontSize: '0.65rem' }} />}
                      {spotResults.tpuInfo.specs?.hbm_gb && <Chip label={`${spotResults.tpuInfo.specs.hbm_gb} GB HBM`} size="small" sx={{ height: 22, fontSize: '0.65rem' }} />}
                    </Box>
                  </Alert>
                )}
                {spotResults.recommendations.length > 0 ? (
                  <TableContainer>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>Region</TableCell>
                          <TableCell>Zone</TableCell>
                          <TableCell>Availability</TableCell>
                          <TableCell>Preemption Risk</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {spotResults.recommendations.map((rec, idx) => (
                          <TableRow key={idx} hover>
                            <TableCell>{rec.region}</TableCell>
                            <TableCell sx={{ fontWeight: 500 }}>{rec.zone}</TableCell>
                            <TableCell><AvailabilityChip availability={rec.spotAvailability} /></TableCell>
                            <TableCell><PreemptionChip rate={rec.preemptionRate} /></TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                ) : (
                  <Alert severity="warning">No spot advisory recommendations found.</Alert>
                )}
                {spotResults.errors?.length > 0 && (
                  <Box sx={{ mt: 2 }}>
                    <Button size="small" onClick={() => setShowSpotErrors(!showSpotErrors)}
                      endIcon={showSpotErrors ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                      sx={{ color: '#d93025', fontSize: '0.75rem' }}>
                      {spotResults.errors.length} zone error(s)
                    </Button>
                    <Collapse in={showSpotErrors}>
                      <Box sx={{ mt: 1 }}>
                        {spotResults.errors.map((err, idx) => (
                          <Alert key={idx} severity="warning" sx={{ mb: 0.5, py: 0, '& .MuiAlert-message': { fontSize: '0.75rem' } }}>{err}</Alert>
                        ))}
                      </Box>
                    </Collapse>
                  </Box>
                )}
              </>
            )}

            {!spotResults && !spotLoading && !spotError && !machineType && (
              <Box sx={{ textAlign: 'center', py: 3, color: '#80868b' }}>
                <BoltIcon sx={{ fontSize: 40, mb: 1, opacity: 0.3 }} />
                <Typography variant="body2">Select a machine type above first</Typography>
              </Box>
            )}
          </Paper>
        </Grid>
      </Grid>
    </Box>
  )
}

function AvailabilityChip({ availability }) {
  const avail = (availability || '').toUpperCase()
  if (avail.includes('HIGH') || avail === 'AVAILABLE') return <Chip label={availability} size="small" color="success" sx={{ height: 22, fontSize: '0.65rem' }} />
  if (avail.includes('MEDIUM') || avail.includes('MODERATE')) return <Chip label={availability} size="small" color="warning" sx={{ height: 22, fontSize: '0.65rem' }} />
  if (avail.includes('LOW') || avail === 'UNAVAILABLE') return <Chip label={availability} size="small" color="error" sx={{ height: 22, fontSize: '0.65rem' }} />
  return <Chip label={availability || 'UNKNOWN'} size="small" sx={{ height: 22, fontSize: '0.65rem' }} />
}

function PreemptionChip({ rate }) {
  const r = (rate || '').toUpperCase()
  if (r.includes('LOW') || r.includes('MINIMAL')) return <Chip label={rate} size="small" color="success" sx={{ height: 22, fontSize: '0.65rem' }} />
  if (r.includes('MEDIUM') || r.includes('MODERATE')) return <Chip label={rate} size="small" color="warning" sx={{ height: 22, fontSize: '0.65rem' }} />
  if (r.includes('HIGH')) return <Chip label={rate} size="small" color="error" sx={{ height: 22, fontSize: '0.65rem' }} />
  return <Chip label={rate || 'UNKNOWN'} size="small" sx={{ height: 22, fontSize: '0.65rem' }} />
}
