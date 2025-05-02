import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  Box,
  Button,
  Typography,
  Container,
  Paper,
  CircularProgress,
} from '@mui/material';
import { useAuth } from '../contexts/AuthContext';

const Login = () => {
  const { login, handleCallback, error } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [isLoading, setIsLoading] = useState(false);
  const hasCalledCallback = useRef(false);

  useEffect(() => {
    const query = new URLSearchParams(location.search);
    const code = query.get('code');
    const state = query.get('state');

    if (code && !hasCalledCallback.current) {
      console.log('Authorization code detected, processing callback...');
      hasCalledCallback.current = true;
      setIsLoading(true);

      handleCallback(code, state)
        .then(() => {
          console.log('OAuth callback handling complete, navigating...');
          navigate('/');
        })
        .catch(err => {
          console.error('OAuth callback handling failed:', err);
        })
        .finally(() => {
          setIsLoading(false);
        });
    }
  }, [location, handleCallback, navigate]);

  const handleLogin = async (e) => {
    if (e) e.preventDefault(); // Prevents page reload
    localStorage.removeItem('bungie_token');
    localStorage.removeItem('oauth_state');
    setIsLoading(true);
    await login();
    setIsLoading(false);
  };

  return (
    <Container component="main" maxWidth="sm">
      <Box
        sx={{
          marginTop: 8,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
        }}
      >
        <Paper
          elevation={3}
          sx={{
            p: 4,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            background: 'rgba(13, 13, 13, 0.8)',
            backdropFilter: 'blur(10px)',
            border: '1px solid',
            borderColor: 'primary.main',
            borderRadius: 2,
          }}
        >
          <Typography component="h1" variant="h4" gutterBottom>
            Welcome Guardian
          </Typography>
          
          <Typography variant="body1" sx={{ mb: 3, textAlign: 'center' }}>
            Track your Destiny 2 catalyst progress and never miss a completion.
          </Typography>

          <Button
            variant="contained"
            color="primary"
            onClick={handleLogin}
            type="button"
            disabled={isLoading}
            sx={{
              mt: 2,
              py: 1.5,
              px: 4,
              borderRadius: 2,
              textTransform: 'none',
              fontSize: '1.1rem',
              '&:hover': {
                boxShadow: '0 0 15px',
              },
            }}
          >
            {isLoading ? (
              <CircularProgress size={24} color="inherit" />
            ) : (
              'Sign in with Bungie'
            )}
          </Button>

          {error && (
            <Typography color="error" sx={{ mt: 2 }}>
              {error}
            </Typography>
          )}
        </Paper>
      </Box>
    </Container>
  );
};

export default Login; 