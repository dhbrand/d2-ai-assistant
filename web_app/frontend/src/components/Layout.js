import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  AppBar,
  Box,
  Toolbar,
  Typography,
  IconButton,
  useTheme,
  Container,
  Button,
} from '@mui/material';
import {
  Brightness4 as DarkIcon,
  Brightness7 as LightIcon,
  Menu as MenuIcon,
} from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';

const Layout = ({ children }) => {
  const theme = useTheme();
  const { isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [isDark, setIsDark] = useState(true);

  const handleThemeToggle = () => {
    setIsDark(!isDark);
    // Theme toggle logic will be implemented later
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  // If on chat page, render only children (no header/footer/container)
  if (location.pathname === '/') {
    return children;
  }

  // For all other pages, render header, container, and footer
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <AppBar position="sticky" sx={{ background: 'transparent', backdropFilter: 'blur(10px)' }}>
        <Toolbar>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            Ghost Terminal
          </Typography>
          {isAuthenticated && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Button
                color="inherit"
                onClick={() => navigate('/')}
              >
                Dashboard
              </Button>
              <Button
                color="inherit"
                onClick={handleLogout}
              >
                Logout
              </Button>
            </Box>
          )}
          <IconButton
            color="inherit"
            onClick={handleThemeToggle}
            sx={{ ml: 2 }}
          >
            {isDark ? <LightIcon /> : <DarkIcon />}
          </IconButton>
        </Toolbar>
      </AppBar>
      <Container component="main" sx={{ mt: 4, mb: 4, flex: 1 }}>
        {children}
      </Container>
      <Box
        component="footer"
        sx={{
          py: 3,
          px: 2,
          mt: 'auto',
          backgroundColor: theme.palette.background.paper,
        }}
      >
        <Container maxWidth="sm">
          <Typography variant="body2" color="text.secondary" align="center">
            © {new Date().getFullYear()} Destiny 2 Catalyst Tracker
          </Typography>
        </Container>
      </Box>
    </Box>
  );
};

export default Layout; 