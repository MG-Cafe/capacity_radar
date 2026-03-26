
import React, { useState, useMemo } from 'react'
import {
  Box, Paper, Typography, Grid, TextField, MenuItem, Button,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Alert, AlertTitle, CircularProgress, Chip, Card, CardContent,
  FormControl, InputLabel, Select, OutlinedInput, Checkbox,
  ListItemText, Divider, Tooltip, IconButton, Collapse,
  FormControlLabel, Switch,
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

  // Calendar-specific params (simplified)
  const [vmCount, setVmCount] = useState(1)
  const [durationDays, setDurationDays] = useState(7)
  const [startDate, setStartDate] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() + 1)
    return d.toISOString().split('T')[0]
  })
  const [flexibilityDays, setFlexibilityDays] = useState(0)

  // Results state
  const [calendarResults, setCalendarResults] = useState(null)
  const [splitsResults, setSplitsResults] = useState(null)
  const [spotResults, setSpotResults] = useState(null)
  const [calendarLoading, setCalendarLoading] = useState(false)
  const [splitsLoading, setSplitsLoading] = useState(false)
  const [spotLoading, setSpotLoading] = useState(false)
  const [calendarError, setCalendarError] = useState(null)
  const [splitsError, setSplitsError] = useState(null)
  const [spotError, setSpotError] = useState(null)
  const [showCalendarErrors, setShowCalendarErrors] = useState(false)
  const [showSpotErrors, setShowSpotErrors] = useState(false)
  const [showUnsupported, setShowUnsupported] = useState(false)
  const [calendarQueryInfo, setCalendarQueryInfo] = useState(null)

  const selectedMachineInfo = useMemo(() => {
    return machineTypes.find(mt => mt.machineType === machineType)
  }, [machineType, machineTypes])

  const availableZones = useMemo(() => selectedMachineInfo?.zones || [], [selectedMachineInfo])

  const handleZoneChange = (event) => {
    setSelectedZones(typeof event.target.value === 'string' ? event.target.value.split(',') : event.target.value)
  }

  const getZonesAndRegions = () => {
    const zones = selectedZones.length > 0 ? selectedZones : availableZones
    const regions = [...new Set(zones.map(z => z.split('-').slice(0, -1).join('-')))].filter(Boolean)
    return { zones, regions }
  }

  const queryCalendarAdvisory = async () => {
    setCalendarLoading(true)
    setCalendarError(null)
    setCalendarResults(null)
    setSplitsResults(null)
    setCalendarQueryInfo({
      mode: 'check',
      startDate,
      flexibilityDays,
      durationDays,
    })
    try {
      const { zones, regions } = getZonesAndRegions()
      const resp = await fetch('/api/advisory/calendar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project, machineType, vmCount,
          startDate, flexibilityDays, durationDays,
          regions, zones,
        }),
      })
      if (!resp.ok) {
        let errMsg = `HTTP ${resp.status}`
        try { const err = await resp.json(); errMsg = err.detail || errMsg } catch { /* non-JSON */ }
        throw new Error(errMsg)
      }
      setCalendarResults(await resp.json())
    } catch (e) {
      setCalendarError(e.message)
    } finally {
      setCalendarLoading(false)
    }
  }

  const findBestPlan = async () => {
    setSplitsLoading(true)
    setSplitsError(null)
    setSplitsResults(null)
    setCalendarResults(null)
    setCalendarQueryInfo({
      mode: 'splits',
      startDate,
      flexibilityDays,
      durationDays,
      vmCount,
    })
    try {
      const { zones, regions } = getZonesAndRegions()
      const resp = await fetch('/api/advisory/calendar/splits', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project, machineType, vmCount,
          startDate, flexibilityDays, durationDays,
          regions, zones,
        }),
      })
      if (!resp.ok) {
        let errMsg = `HTTP ${resp.status}`
        try { const err = await resp.json(); errMsg = err.detail || errMsg } catch { /* non-JSON */ }
        throw new Error(errMsg)
      }
      setSplitsResults(await resp.json())
    } catch (e) {
      setSplitsError(e.message)
    } finally {
      setSplitsLoading(false)
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
        let errMsg = `HTTP ${resp.status}`
        try { const err = await resp.json(); errMsg = err.detail || errMsg } catch { /* non-JSON */ }
        throw new Error(errMsg)
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
  const anyLoading = calendarLoading || splitsLoading

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

        {/* Show unsupported toggle */}
        {machineType && (
          <Box sx={{ mb: 1.5, mt: 1.5, display: 'flex', alignItems: 'center', gap: 1 }}>
            <FormControlLabel
              control={
                <Switch
                  checked={showUnsupported}
                  onChange={(e) => { setShowUnsupported(e.target.checked); setSelectedZones([]) }}
                  size="small"
                />
              }
              label={
                <Typography variant="caption" sx={{ color: '#5f6368', fontSize: '0.72rem' }}>
                  {showUnsupported ? 'Showing all methods & zones' : 'Showing only supported methods & zones'}
                </Typography>
              }
            />
            <Tooltip title="When off, only shows zones and consumption models that are officially supported for this chip. Enable to see all options.">
              <InfoOutlinedIcon sx={{ fontSize: 14, color: '#80868b', cursor: 'help' }} />
            </Tooltip>
          </Box>
        )}

        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} md={5}>
            <FormControl fullWidth size="small">
              <InputLabel>Zones (optional filter)</InputLabel>
              <Select
                multiple
                value={selectedZones}
                onChange={handleZoneChange}
                input={<OutlinedInput label="Zones (optional filter)" />}
                renderValue={(selected) => selected.length === 0 ? 'All supported zones' : `${selected.length} zones selected`}
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
                {Object.entries(selectedMachineInfo.supported)
                  .filter(([key, supported]) => showUnsupported || supported)
                  .map(([key, supported]) => {
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
        {(showUnsupported || !machineType || supportsCalendar) && (
        <Grid item xs={12} lg={6}>
          <Paper sx={{ p: 3, height: '100%' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
              <CalendarMonthIcon sx={{ color: '#1a73e8', fontSize: 22 }} />
              <Typography variant="h4">DWS Calendar Advisory</Typography>
              <Tooltip title="Shows recommended zones and time windows for DWS Calendar mode reservations. Supported for A3, A4, and TPU families.">
                <InfoOutlinedIcon sx={{ fontSize: 16, color: '#80868b', cursor: 'help' }} />
              </Tooltip>
              {anyLoading && <CircularProgress size={18} sx={{ ml: 'auto' }} />}
            </Box>

            {!selectedMachineInfo?.supported?.dws_calendar && machineType && (
              <Alert severity="info" sx={{ mb: 2 }}>
                DWS Calendar mode is not supported for {machineType}. Only available for A4, A3, and TPU types.
              </Alert>
            )}

            {/* Calendar inputs — simplified */}
            {(supportsCalendar || !machineType) && (
              <Box sx={{ bgcolor: '#e8f0fe', borderRadius: 2, p: 2, mb: 2 }}>
                <Grid container spacing={1.5}>
                  <Grid item xs={6} sm={3}>
                    <TextField fullWidth type="number" label="VM Count" value={vmCount}
                      onChange={(e) => setVmCount(Math.max(1, parseInt(e.target.value) || 1))}
                      size="small" inputProps={{ min: 1 }} />
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <TextField fullWidth type="number" label="Duration (days)" value={durationDays}
                      onChange={(e) => setDurationDays(Math.max(1, parseInt(e.target.value) || 1))}
                      size="small" inputProps={{ min: 1, max: 365 }}
                      helperText="How long you need GPUs" />
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <TextField fullWidth type="date" label="Start Date" value={startDate}
                      onChange={(e) => setStartDate(e.target.value)} size="small"
                      InputLabelProps={{ shrink: true }}
                      helperText="When to start" />
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <TextField fullWidth select label="Flexibility" value={flexibilityDays}
                      onChange={(e) => setFlexibilityDays(parseInt(e.target.value))} size="small"
                      helperText="Start date flexibility">
                      <MenuItem value={0}>None (exact date)</MenuItem>
                      <MenuItem value={1}>+/- 1 day</MenuItem>
                      <MenuItem value={2}>+/- 2 days</MenuItem>
                      <MenuItem value={3}>+/- 3 days</MenuItem>
                    </TextField>
                  </Grid>
                </Grid>
                <Box sx={{ display: 'flex', gap: 1, mt: 1.5 }}>
                  <Button
                    variant="contained" sx={{ flex: 1 }}
                    onClick={queryCalendarAdvisory}
                    disabled={!canQuery || anyLoading || !supportsCalendar}
                    startIcon={calendarLoading ? <CircularProgress size={16} /> : <CalendarMonthIcon />}
                  >
                    Check Availability
                  </Button>
                  <Tooltip title="Analyze capacity at different VM counts to build a deployment plan with sub-duration splits" arrow>
                    <span>
                      <Button
                        variant="outlined" sx={{ flex: 1 }}
                        onClick={findBestPlan}
                        disabled={!canQuery || anyLoading || !supportsCalendar}
                        startIcon={splitsLoading ? <CircularProgress size={16} /> : <SearchIcon />}
                      >
                        Find Best Plan
                      </Button>
                    </span>
                  </Tooltip>
                </Box>
              </Box>
            )}

            {calendarError && (
              <Alert severity="error" sx={{ mb: 2 }}>
                <AlertTitle>Calendar Advisory Error</AlertTitle>
                {calendarError}
              </Alert>
            )}
            {splitsError && (
              <Alert severity="error" sx={{ mb: 2 }}>
                <AlertTitle>Capacity Plan Error</AlertTitle>
                {splitsError}
              </Alert>
            )}

            {/* Check Availability results */}
            {calendarResults && (
              <>
                {calendarQueryInfo && (
                  <Alert severity="success"
                    icon={<CalendarMonthIcon />}
                    sx={{ mb: 2, py: 0.5, '& .MuiAlert-message': { fontSize: '0.78rem' } }}>
                    <strong>Check Availability:</strong>{' '}
                    {calendarQueryInfo.startDate}
                    {calendarQueryInfo.flexibilityDays > 0 && ` (+/- ${calendarQueryInfo.flexibilityDays}d)`}
                    {' | '}{calendarQueryInfo.durationDays} days
                    {(() => {
                      const recs = calendarResults.recommendations || []
                      const recCount = recs.filter(r => r.status === 'RECOMMENDED').length
                      const noCapCount = recs.filter(r => r.status === 'NO_CAPACITY').length
                      return <> | <strong>{recCount} recommended</strong>, {noCapCount} no capacity</>
                    })()}
                  </Alert>
                )}
                {calendarResults.tpuInfo && (
                  <TpuInfoAlert info={calendarResults.tpuInfo} message={calendarResults.message} />
                )}
                <CalendarRecsTable
                  recommendations={calendarResults.recommendations || []}
                  showUnsupported={showUnsupported}
                />
                <ErrorsCollapse errors={calendarResults.errors}
                  show={showCalendarErrors} setShow={setShowCalendarErrors} />
              </>
            )}

            {/* Find Best Plan results */}
            {splitsResults && (
              <>
                {splitsResults.tpuInfo ? (
                  <TpuInfoAlert info={splitsResults.tpuInfo} message={splitsResults.message} />
                ) : (
                  <>
                    <Alert severity="info" sx={{ mb: 2 }}>
                      <AlertTitle>Capacity Plan</AlertTitle>
                      <Typography variant="body2">{splitsResults.summary}</Typography>
                    </Alert>
                    {(splitsResults.splits || []).map((split, idx) => {
                      const recommended = (split.recommendations || []).filter(r => r.status === 'RECOMMENDED')
                      return (
                        <Box key={idx} sx={{ mb: 2 }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                            <Chip
                              label={`${split.vmCount} VMs (${split.percentOfRequested}%)`}
                              size="small"
                              color={split.percentOfRequested === 100 ? 'success' : 'warning'}
                              sx={{ height: 24, fontSize: '0.7rem', fontWeight: 600 }}
                            />
                            <Typography variant="caption" color="text.secondary">
                              {recommended.length > 0
                                ? `${recommended.length} zone(s) with capacity`
                                : 'No availability'}
                            </Typography>
                          </Box>
                          {recommended.length > 0 ? (
                            <TableContainer sx={{ maxHeight: 200 }}>
                              <Table size="small">
                                <TableHead>
                                  <TableRow>
                                    <TableCell>Zone</TableCell>
                                    <TableCell>Start</TableCell>
                                    <TableCell>End</TableCell>
                                  </TableRow>
                                </TableHead>
                                <TableBody>
                                  {recommended.map((rec, ridx) => (
                                    <TableRow key={ridx} hover sx={{ bgcolor: '#e6f4ea' }}>
                                      <TableCell sx={{ fontWeight: 500 }}>{rec.zone}</TableCell>
                                      <TableCell sx={{ fontSize: '0.75rem' }}>
                                        {rec.startTime ? new Date(rec.startTime).toLocaleDateString() : '—'}
                                      </TableCell>
                                      <TableCell sx={{ fontSize: '0.75rem' }}>
                                        {rec.endTime ? new Date(rec.endTime).toLocaleDateString() : '—'}
                                      </TableCell>
                                    </TableRow>
                                  ))}
                                </TableBody>
                              </Table>
                            </TableContainer>
                          ) : (
                            <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                              No capacity at this VM count in the specified window.
                            </Typography>
                          )}
                        </Box>
                      )
                    })}
                  </>
                )}
                <ErrorsCollapse errors={splitsResults.errors}
                  show={showCalendarErrors} setShow={setShowCalendarErrors} />
              </>
            )}

            {!calendarResults && !splitsResults && !anyLoading && !calendarError && !splitsError && !machineType && (
              <Box sx={{ textAlign: 'center', py: 3, color: '#80868b' }}>
                <CalendarMonthIcon sx={{ fontSize: 40, mb: 1, opacity: 0.3 }} />
                <Typography variant="body2">Select a machine type above first</Typography>
              </Box>
            )}
          </Paper>
        </Grid>
        )}

        {/* Spot Advisory */}
        {(showUnsupported || !machineType || selectedMachineInfo?.supported?.spot !== false) && (
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
                  <TpuInfoAlert info={spotResults.tpuInfo} message={spotResults.message} />
                )}
                {(spotResults.recommendations || []).length > 0 ? (
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
                        {(spotResults.recommendations || []).map((rec, idx) => (
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
                <ErrorsCollapse errors={spotResults.errors}
                  show={showSpotErrors} setShow={setShowSpotErrors} />
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
        )}
      </Grid>
    </Box>
  )
}

// --- Helper components ---

function CalendarRecsTable({ recommendations, showUnsupported }) {
  const validStatuses = ['RECOMMENDED', 'NO_CAPACITY', 'NO_DATA']
  const filteredRecs = showUnsupported
    ? recommendations
    : recommendations.filter(r => validStatuses.includes(r.status))
  const hiddenCount = recommendations.length - filteredRecs.length

  if (filteredRecs.length === 0) {
    return (
      <Alert severity="warning">
        {recommendations.length > 0
          ? `No supported zone results found. ${recommendations.length} unsupported zone(s) hidden. Enable "Show all" toggle to see them.`
          : 'No calendar advisory recommendations found.'}
      </Alert>
    )
  }

  return (
    <>
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
            {filteredRecs
              .sort((a, b) => {
                if (a.status === 'RECOMMENDED' && b.status !== 'RECOMMENDED') return -1
                if (a.status !== 'RECOMMENDED' && b.status === 'RECOMMENDED') return 1
                return 0
              })
              .map((rec, idx) => (
              <TableRow key={idx} hover sx={rec.status === 'RECOMMENDED' ? { bgcolor: '#e6f4ea' } : {}}>
                <TableCell sx={{ fontWeight: 500 }}>{rec.zone}</TableCell>
                <TableCell>
                  <Chip label={rec.status || 'UNKNOWN'} size="small"
                    color={rec.status === 'RECOMMENDED' ? 'success' : rec.status === 'NO_CAPACITY' ? 'error' : 'default'}
                    sx={{ height: 22, fontSize: '0.65rem' }} />
                </TableCell>
                <TableCell sx={{ fontSize: '0.75rem', color: '#5f6368' }}>
                  {rec.details || (rec.status === 'RECOMMENDED' ? 'Capacity available' : '—')}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      {hiddenCount > 0 && !showUnsupported && (
        <Typography variant="caption" sx={{ mt: 1, display: 'block', color: '#80868b', fontSize: '0.68rem' }}>
          {hiddenCount} unsupported zone(s) hidden. Enable "Show all" toggle to see them.
        </Typography>
      )}
    </>
  )
}

function TpuInfoAlert({ info, message }) {
  return (
    <Alert severity="info" sx={{ mb: 2, '& .MuiAlert-message': { fontSize: '0.8rem', width: '100%' } }}>
      <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5 }}>
        {info.name} — {info.machineType}
      </Typography>
      <Typography variant="body2" sx={{ mb: 1 }}>{message}</Typography>
      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 1 }}>
        {info.specs?.chips && <Chip label={`${info.specs.chips} chips`} size="small" sx={{ height: 22, fontSize: '0.65rem' }} />}
        {info.specs?.vcpus && <Chip label={`${info.specs.vcpus} vCPUs`} size="small" sx={{ height: 22, fontSize: '0.65rem' }} />}
        {info.specs?.memory_gb && <Chip label={`${info.specs.memory_gb} GB RAM`} size="small" sx={{ height: 22, fontSize: '0.65rem' }} />}
        {info.specs?.hbm_gb && <Chip label={`${info.specs.hbm_gb} GB HBM`} size="small" sx={{ height: 22, fontSize: '0.65rem' }} />}
      </Box>
      <Typography variant="caption" color="text.secondary">
        <strong>Zones:</strong> {info.zones?.join(', ')}
      </Typography>
      {info.topologies?.length > 0 && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
          <strong>Topologies:</strong> {info.topologies.join(', ')}
        </Typography>
      )}
      <Box sx={{ display: 'flex', gap: 0.5, mt: 1, flexWrap: 'wrap' }}>
        <Chip label="On-Demand" size="small" color={info.supported?.on_demand ? 'success' : 'default'} variant="outlined" sx={{ height: 20, fontSize: '0.6rem' }} />
        <Chip label="Spot" size="small" color={info.supported?.spot ? 'success' : 'default'} variant="outlined" sx={{ height: 20, fontSize: '0.6rem' }} />
        <Chip label="DWS Calendar" size="small" color={info.supported?.dws_calendar ? 'success' : 'default'} variant="outlined" sx={{ height: 20, fontSize: '0.6rem' }} />
        <Chip label="DWS Flex" size="small" color={info.supported?.dws_flex ? 'success' : 'default'} variant="outlined" sx={{ height: 20, fontSize: '0.6rem' }} />
      </Box>
    </Alert>
  )
}

function ErrorsCollapse({ errors, show, setShow }) {
  if (!errors || errors.length === 0) return null
  return (
    <Box sx={{ mt: 2 }}>
      <Button size="small" onClick={() => setShow(!show)}
        endIcon={show ? <ExpandLessIcon /> : <ExpandMoreIcon />}
        sx={{ color: '#d93025', fontSize: '0.75rem' }}>
        {errors.length} zone error(s)
      </Button>
      <Collapse in={show}>
        <Box sx={{ mt: 1 }}>
          {errors.map((err, idx) => (
            <Alert key={idx} severity="warning" sx={{ mb: 0.5, py: 0, '& .MuiAlert-message': { fontSize: '0.75rem' } }}>{err}</Alert>
          ))}
        </Box>
      </Collapse>
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
