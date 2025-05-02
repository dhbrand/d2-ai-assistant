import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import {
  Button,
  Container,
  Typography,
  Box,
  Paper,
  CircularProgress,
  Alert,
} from '@mui/material';

const Login = () => {
  const { login, handleCallback, isAuthenticated, error } = useAuth();
  const [isLoading, setIsLoading] = useState(false);
  const [localError, setLocalError] = useState(null);
  const navigate = useNavigate();
  const location = useLocation();
  const hasCalledCallback = useRef(false);

  // Clear any lingering tokens on component mount
  useEffect(() => {
    // This helps with Safari's aggressive caching
    const cleanupSafariCache = () => {
      try {
        // Remove specific Safari cookie behavior issues by clearing
        // these items - especially important for regular windows
        localStorage.removeItem('bungie_token');
        localStorage.removeItem('oauth_state');
        
        // Force clear cookie path for localhost
        document.cookie = 'bungie_oauth=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
      } catch (e) {
        console.error('Error cleaning up Safari cache:', e);
      }
    };
    
    // Only clean up if this is a fresh login, not a callback
    if (!location.search || !location.search.includes('code=')) {
      cleanupSafariCache();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const query = new URLSearchParams(location.search);
    const code = query.get('code');
    const state = query.get('state');
    const error = query.get('error');
    
    // Handle error parameter from OAuth provider
    if (error) {
      setLocalError(`Authentication error: ${error}`);
      setIsLoading(false);
      return;
    }

    // Only handle callback if code exists and hasn't been processed yet
    if (code && state && !hasCalledCallback.current) {
      console.log('Login: Authorization code detected, processing callback...');
      hasCalledCallback.current = true; // Mark as processed
      setIsLoading(true);

      handleCallback(code, state)
        .then(() => {
          console.log('Login: OAuth callback handling complete');
          navigate('/');
        })
        .catch(err => {
          console.error('Login: OAuth callback handling failed:', err);
          setLocalError('Authentication failed. Please try again or use an incognito window.');
        })
        .finally(() => {
          setIsLoading(false);
        });
    }
  }, [location, handleCallback, navigate]);

  // Redirect to dashboard if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/');
    }
  }, [isAuthenticated, navigate]);

  const handleLogin = async (e) => {
    if (e) e.preventDefault(); // Prevents page reload
    
    // Clear errors before starting new login
    setLocalError(null);
    
    setIsLoading(true);
    try {
      await login();
      // Note: No need to navigate here as login() redirects to Bungie
    } catch (err) {
      setLocalError('Failed to initiate login. Please try again.');
      setIsLoading(false);
    }
  };

  return (
    <Container maxWidth="sm">
      <Box sx={{ mt: 8, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <Paper
          elevation={3}
          sx={{
            p: 4,
            width: '100%',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            background: 'rgba(13, 13, 13, 0.8)',
            backdropFilter: 'blur(10px)',
          }}
        >
          <Typography variant="h4" component="h1" gutterBottom>
            Destiny 2 Catalyst Tracker
          </Typography>
          
          <Typography variant="body1" sx={{ mb: 4, textAlign: 'center' }}>
            Track your Destiny 2 catalyst progress and never miss a completion
          </Typography>
          
          {(error || localError) && (
            <Alert severity="error" sx={{ mb: 3, width: '100%' }}>
              {error || localError}
            </Alert>
          )}
          
          <Button
            onClick={handleLogin}
            type="button"
            variant="contained"
            color="primary"
            size="large"
            disabled={isLoading}
            sx={{
              py: 1.5,
              fontSize: '1.1rem',
              width: '100%',
              maxWidth: 300,
              borderRadius: 2,
            }}
          >
            {isLoading ? (
              <CircularProgress size={24} color="inherit" />
            ) : (
              'Sign in with Bungie'
            )}
          </Button>
          
          <Typography variant="body2" sx={{ mt: 2, opacity: 0.7, textAlign: 'center' }}>
            For the best experience, try using an incognito/private window.
          </Typography>
        </Paper>
      </Box>
    </Container>
  );
};

export default Login; 