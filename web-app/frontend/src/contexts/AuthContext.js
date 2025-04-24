import React, { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';

const AuthContext = createContext(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    checkAuthStatus();
  }, []);

  const checkAuthStatus = async () => {
    try {
      const token = localStorage.getItem('bungie_token');
      if (token) {
        // Verify token with backend
        await axios.get('/api/auth/verify', {
          headers: { Authorization: `Bearer ${token}` }
        });
        setIsAuthenticated(true);
      }
    } catch (err) {
      console.error('Auth verification failed:', err);
      localStorage.removeItem('bungie_token');
      setIsAuthenticated(false);
    } finally {
      setIsLoading(false);
    }
  };

  const login = async () => {
    try {
      const response = await axios.get('/api/auth/url');
      window.location.href = response.data.auth_url;
    } catch (err) {
      setError('Failed to initiate authentication');
      console.error('Login error:', err);
    }
  };

  const handleCallback = async (code) => {
    try {
      const response = await axios.post('/api/auth/callback', { code });
      localStorage.setItem('bungie_token', response.data.token_data.access_token);
      setIsAuthenticated(true);
      setError(null);
    } catch (err) {
      setError('Authentication failed');
      console.error('Callback error:', err);
    }
  };

  const logout = () => {
    localStorage.removeItem('bungie_token');
    setIsAuthenticated(false);
  };

  const value = {
    isAuthenticated,
    isLoading,
    error,
    login,
    handleCallback,
    logout,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}; 