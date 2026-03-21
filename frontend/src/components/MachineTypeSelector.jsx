import React, { useMemo } from 'react'
import {
  Box, TextField, MenuItem, Chip, Typography, ToggleButton,
  ToggleButtonGroup, Tooltip,
} from '@mui/material'
import MemoryIcon from '@mui/icons-material/Memory'
import DeveloperBoardIcon from '@mui/icons-material/DeveloperBoard'

/**
 * Multi-step machine type selector:
 * 1. GPU or TPU (toggle)
 * 2. Chip/Accelerator type (dropdown)
 * 3. VM Configuration (dropdown)
 */
export default function MachineTypeSelector({
  machineTypes = [],
  category, setCategory,
  chip, setChip,
  machineType, setMachineType,
  disabled = false,
  size = 'small',
}) {
  // Group by chip
  const chipGroups = useMemo(() => {
    const groups = {}
    machineTypes.forEach(mt => {
      const c = mt.chip || mt.gpu
      const cat = mt.category || 'GPU'
      if (cat !== category) return
      if (!groups[c]) {
        groups[c] = { chip: c, gpu: mt.gpu, types: [] }
      }
      groups[c].types.push(mt)
    })
    return groups
  }, [machineTypes, category])

  const chipList = useMemo(() => Object.values(chipGroups), [chipGroups])

  const selectedChipGroup = useMemo(() => chipGroups[chip] || null, [chipGroups, chip])

  const filteredMachineTypes = useMemo(() => {
    if (!selectedChipGroup) return []
    return selectedChipGroup.types
  }, [selectedChipGroup])

  const selectedMachineInfo = useMemo(() => {
    return machineTypes.find(mt => mt.machineType === machineType)
  }, [machineType, machineTypes])

  return (
    <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'flex-end' }}>
      {/* Step 1: GPU or TPU */}
      <Box sx={{ pb: '20px' }}>
        <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block', fontSize: '0.7rem' }}>
          Accelerator Type
        </Typography>
        <ToggleButtonGroup
          value={category}
          exclusive
          onChange={(_, val) => {
            if (val) {
              setCategory(val)
              setChip('')
              setMachineType('')
            }
          }}
          size="small"
          disabled={disabled}
          sx={{ height: 40 }}
        >
          <ToggleButton value="GPU" sx={{ px: 2.5, textTransform: 'none', fontWeight: 500, gap: 0.5 }}>
            <MemoryIcon sx={{ fontSize: 16 }} /> GPU
          </ToggleButton>
          <ToggleButton value="TPU" sx={{ px: 2.5, textTransform: 'none', fontWeight: 500, gap: 0.5 }}>
            <DeveloperBoardIcon sx={{ fontSize: 16 }} /> TPU
          </ToggleButton>
        </ToggleButtonGroup>
      </Box>

      {/* Step 2: Chip selection */}
      <Box sx={{ minWidth: 200 }}>
        <TextField
          fullWidth
          select
          label={category === 'GPU' ? 'GPU Chip' : 'TPU Version'}
          value={chip}
          onChange={(e) => {
            setChip(e.target.value)
            setMachineType('')
          }}
          size={size}
          disabled={disabled}
          helperText={selectedChipGroup ? `${selectedChipGroup.types.length} config(s)` : `Select ${category} type`}
        >
          {chipList.map(cg => (
            <MenuItem key={cg.chip} value={cg.chip}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
                <Chip
                  label={cg.chip}
                  size="small"
                  sx={{
                    bgcolor: '#e8f0fe', color: '#1a73e8', fontWeight: 600,
                    height: 22, fontSize: '0.7rem',
                  }}
                />
                <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.75rem' }}>
                  {cg.types.length} config{cg.types.length > 1 ? 's' : ''}
                </Typography>
              </Box>
            </MenuItem>
          ))}
        </TextField>
      </Box>

      {/* Step 3: VM Configuration */}
      <Box sx={{ minWidth: 220 }}>
        <TextField
          fullWidth
          select
          label="VM Configuration"
          value={machineType}
          onChange={(e) => setMachineType(e.target.value)}
          size={size}
          disabled={disabled || !chip}
          helperText={
            selectedMachineInfo
              ? (selectedMachineInfo.category === 'TPU'
                  ? `${selectedMachineInfo.gpuCount} chip(s) · ${selectedMachineInfo.vcpus || '?'} vCPUs · ${selectedMachineInfo.hbmGb || '?'} GB HBM`
                  : `${selectedMachineInfo.gpu} × ${selectedMachineInfo.gpuCount}`)
              : chip ? 'Select a configuration' : 'Select chip first'
          }
        >
          {filteredMachineTypes.map(mt => (
            <MenuItem key={mt.machineType} value={mt.machineType}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', width: '100%', alignItems: 'center', gap: 1 }}>
                <Box>
                  <Typography variant="body2" sx={{ fontWeight: 500, lineHeight: 1.2 }}>
                    {mt.machineType}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem' }}>
                    {mt.category === 'TPU'
                      ? `${mt.gpuCount} chips · ${mt.vcpus || '?'} vCPUs · ${mt.memoryGb || '?'} GB RAM · ${mt.hbmGb || '?'} GB HBM`
                      : mt.family}
                  </Typography>
                </Box>
                <Chip
                  label={mt.category === 'TPU' ? `${mt.gpuCount} chips` : `${mt.gpuCount}× ${mt.chip || ''}`}
                  size="small"
                  sx={{ height: 22, fontSize: '0.65rem', fontWeight: 600 }}
                />
              </Box>
            </MenuItem>
          ))}
        </TextField>
      </Box>

      {/* Selected info chip */}
      {selectedMachineInfo && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, pb: '20px' }}>
          <Tooltip title={`${selectedMachineInfo.gpu} — ${selectedMachineInfo.zones?.length || 0} zones available`}>
            <Chip
              icon={<MemoryIcon sx={{ fontSize: 14 }} />}
              label={`${selectedMachineInfo.chip} × ${selectedMachineInfo.gpuCount} | ${selectedMachineInfo.zones?.length || 0} zones`}
              size="small"
              variant="outlined"
              color="primary"
              sx={{ height: 26, fontSize: '0.72rem', fontWeight: 500 }}
            />
          </Tooltip>
        </Box>
      )}
    </Box>
  )
}
