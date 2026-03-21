import { createTheme } from '@mui/material/styles'

export const theme = createTheme({
  palette: {
    primary: {
      main: '#1a73e8',        // Google Blue
      light: '#4285f4',
      dark: '#1557b0',
      contrastText: '#fff',
    },
    secondary: {
      main: '#5f6368',        // Google Grey
      light: '#80868b',
      dark: '#3c4043',
    },
    success: {
      main: '#1e8e3e',        // Google Green
      light: '#34a853',
      dark: '#137333',
    },
    warning: {
      main: '#f9ab00',        // Google Yellow
      light: '#fbbc04',
      dark: '#e37400',
    },
    error: {
      main: '#d93025',        // Google Red
      light: '#ea4335',
      dark: '#b31412',
    },
    info: {
      main: '#1a73e8',
      light: '#4285f4',
      dark: '#1557b0',
    },
    background: {
      default: '#f8f9fa',     // GCP Console background
      paper: '#ffffff',
    },
    text: {
      primary: '#202124',
      secondary: '#5f6368',
    },
    divider: '#dadce0',
  },
  typography: {
    fontFamily: '"Google Sans", "Roboto", "Helvetica", "Arial", sans-serif',
    h1: {
      fontFamily: '"Google Sans", "Roboto", sans-serif',
      fontWeight: 400,
      fontSize: '2rem',
    },
    h2: {
      fontFamily: '"Google Sans", "Roboto", sans-serif',
      fontWeight: 400,
      fontSize: '1.5rem',
    },
    h3: {
      fontFamily: '"Google Sans", "Roboto", sans-serif',
      fontWeight: 500,
      fontSize: '1.25rem',
    },
    h4: {
      fontFamily: '"Google Sans", "Roboto", sans-serif',
      fontWeight: 500,
      fontSize: '1.1rem',
    },
    h5: {
      fontFamily: '"Google Sans", "Roboto", sans-serif',
      fontWeight: 500,
      fontSize: '1rem',
    },
    h6: {
      fontFamily: '"Google Sans", "Roboto", sans-serif',
      fontWeight: 500,
      fontSize: '0.875rem',
    },
    subtitle1: {
      fontFamily: '"Google Sans", "Roboto", sans-serif',
      fontWeight: 500,
      fontSize: '0.875rem',
      color: '#5f6368',
    },
    body1: {
      fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
      fontSize: '0.875rem',
    },
    body2: {
      fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
      fontSize: '0.8125rem',
    },
    button: {
      fontFamily: '"Google Sans", "Roboto", sans-serif',
      fontWeight: 500,
      textTransform: 'none',
    },
  },
  shape: {
    borderRadius: 8,
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 4,
          padding: '8px 24px',
          fontWeight: 500,
        },
        contained: {
          boxShadow: 'none',
          '&:hover': {
            boxShadow: '0 1px 2px 0 rgba(60,64,67,.3), 0 1px 3px 1px rgba(60,64,67,.15)',
          },
        },
        outlined: {
          borderColor: '#dadce0',
          color: '#1a73e8',
          '&:hover': {
            backgroundColor: '#f0f4ff',
            borderColor: '#1a73e8',
          },
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          border: '1px solid #dadce0',
          boxShadow: 'none',
        },
        elevation1: {
          boxShadow: '0 1px 2px 0 rgba(60,64,67,.3), 0 1px 3px 1px rgba(60,64,67,.15)',
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          border: '1px solid #dadce0',
          boxShadow: 'none',
          '&:hover': {
            boxShadow: '0 1px 2px 0 rgba(60,64,67,.3), 0 2px 6px 2px rgba(60,64,67,.15)',
          },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: 16,
          fontFamily: '"Google Sans", "Roboto", sans-serif',
          fontWeight: 500,
          fontSize: '0.75rem',
        },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontFamily: '"Google Sans", "Roboto", sans-serif',
          fontWeight: 500,
          fontSize: '0.875rem',
          minHeight: 48,
        },
      },
    },
    MuiTabs: {
      styleOverrides: {
        indicator: {
          height: 3,
          borderRadius: '3px 3px 0 0',
        },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          '& .MuiOutlinedInput-root': {
            borderRadius: 4,
          },
        },
      },
    },
    MuiSelect: {
      styleOverrides: {
        root: {
          borderRadius: 4,
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          boxShadow: 'none',
          borderBottom: '1px solid #dadce0',
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        head: {
          fontFamily: '"Google Sans", "Roboto", sans-serif',
          fontWeight: 500,
          color: '#5f6368',
          fontSize: '0.75rem',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
        },
      },
    },
  },
})
