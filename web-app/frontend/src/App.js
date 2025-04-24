import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { AuthProvider } from './contexts/AuthContext';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Login from './pages/Login';
import PrivateRoute from './components/PrivateRoute';

const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#00FFFF',
    },
    secondary: {
      main: '#FF00FF',
    },
    background: {
      default: '#000000',
      paper: '#0D0D0D',
    },
    text: {
      primary: '#FFFFFF',
      secondary: '#00FFFF',
    },
  },
  typography: {
    fontFamily: '"Rajdhani", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    h1: {
      fontWeight: 700,
      fontSize: '2.5rem',
    },
    h2: {
      fontWeight: 600,
      fontSize: '2rem',
    },
    body1: {
      fontSize: '1rem',
    },
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 600,
          letterSpacing: '1px',
        },
      },
    },
  },
});

function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AuthProvider>
        <Router>
          <Layout>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route
                path="/"
                element={
                  <PrivateRoute>
                    <Dashboard />
                  </PrivateRoute>
                }
              />
            </Routes>
          </Layout>
        </Router>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App; 