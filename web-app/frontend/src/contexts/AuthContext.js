import React, { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';

const API_URL = 'https://localhost:8000';
const DEBUG = true; // Enable debug mode

// Configure axios to handle HTTPS requests
axios.defaults.httpsAgent = {
  rejectUnauthorized: false // Note: Only use this in development
};

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
        await axios.get(`${API_URL}/auth/verify`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        setIsAuthenticated(true);
      }
    } catch (err) {
      if (DEBUG) {
        console.error('Auth verification failed:', err.message);
        if (err.response) {
          console.error('Response data:', err.response.data);
          console.error('Response status:', err.response.status);
        }
      }
      localStorage.removeItem('bungie_token');
      setIsAuthenticated(false);
    } finally {
      setIsLoading(false);
    }
  };

  const login = async () => {
    try {
      console.log('AuthContext: Starting login process');
      const response = await axios.get(`${API_URL}/auth/url`);
      console.log('AuthContext: Received response:', response);
      if (response.data && response.data.auth_url) {
        const url = new URL(response.data.auth_url);
        const state = url.searchParams.get('state');
        localStorage.setItem('oauth_state', state);
        console.log('AuthContext: Redirecting to Bungie OAuth page:', response.data.auth_url);
        window.location.href = response.data.auth_url;
      } else {
        console.error('AuthContext: Invalid response data:', response.data);
        throw new Error('No auth_url received from server');
      }
    } catch (err) {
      console.error('AuthContext: Login error:', err);
      setError('Failed to initiate authentication');
      throw err;
    }
  };

  const handleCallback = async (code, state) => {
    try {
      console.log('AuthContext: Handling callback with code and state');
      
      // Get the state parameter from localStorage (sent state)
      // const state = urlParams.get('state'); // No longer need to get from URL here
      const storedState = localStorage.getItem('oauth_state');
      
      console.log('AuthContext: Callback state check:', { 
        receivedState: state, // State received from Bungie
        storedState,       // State we stored before redirect
        stateInLocalStorage: !!localStorage.getItem('oauth_state')
      });
      
      // Log all localStorage items for debugging
      console.log('AuthContext: All localStorage items:');
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        console.log(`- ${key}: ${localStorage.getItem(key)}`);
      }
      
      // Verify state parameter (stricter check recommended for production)
      if (!state || !storedState || state !== storedState) {
         console.error('AuthContext: State mismatch!', { receivedState: state, storedState });
         throw new Error('State parameter mismatch');
         // In development, you might comment out the throw to proceed
         // console.warn('AuthContext: State mismatch, but continuing anyway for development');
      }
      
      // Clear the stored state AFTER verification
      localStorage.removeItem('oauth_state');
      
      console.log('AuthContext: Making callback request to:', `${API_URL}/auth/callback`);
      const response = await axios.post(`${API_URL}/auth/callback`, { code }); // Send only the code
      console.log('AuthContext: Callback response:', response.data);
      
      if (response.data && response.data.token_data && response.data.token_data.access_token) {
        localStorage.setItem('bungie_token', response.data.token_data.access_token);
        console.log('AuthContext: Token stored in localStorage');
        setIsAuthenticated(true);
        setError(null);
        
        // Success message
        console.log('AuthContext: Authentication successful!');
        
        // Redirect to dashboard after successful authentication
        window.location.href = '/';
      } else {
        console.error('AuthContext: Invalid token data received:', response.data);
        throw new Error('Invalid token data received');
      }
    } catch (err) {
      console.error('AuthContext: Callback error details:', {
        message: err.message,
        response: err.response ? {
          data: err.response.data,
          status: err.response.status
        } : 'No response'
      });
      setError('Authentication failed');
      throw err;
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