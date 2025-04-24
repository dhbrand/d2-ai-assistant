import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  Typography,
  Container,
  Paper,
} from '@mui/material';
import { useAuth } from '../contexts/AuthContext';

const Login = () => {
  const { login, error } = useAuth();
  const navigate = useNavigate();

  const handleLogin = async () => {
    try {
      await login();
    } catch (err) {
      console.error('Login failed:', err);
    }
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
            Sign in with Bungie
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