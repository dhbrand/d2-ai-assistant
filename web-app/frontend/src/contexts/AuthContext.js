import React, { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';

const API_URL = 'https://localhost:8000';

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const checkAuthStatus = async () => {
    setIsLoading(true); // Set loading state
    try {
      const token = localStorage.getItem('bungie_token');
      if (!token) {
        setIsAuthenticated(false);
        setIsLoading(false); // Ensure loading stops
        return;
      }
      
      // Check if token is expired based on our stored expiry time
      if (isTokenExpired()) {
        console.log('AuthContext: Token is expired, logging out');
        logout();
        setIsLoading(false); // Ensure loading stops
        return;
      }
      
      const response = await axios.get(`${API_URL}/auth/verify`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (response.data && response.data.status === 'valid') {
        setIsAuthenticated(true);
        setError(null);
      } else {
        // Token invalid according to backend
        console.log('AuthContext: Token invalid according to backend');
        logout();
      }
    } catch (err) {
      console.error('AuthContext: Error checking auth status:', err);
      // Don't immediately logout on network errors
      // This prevents logout on temporary API issues
      if (err.response && (err.response.status === 401 || err.response.status === 403)) {
        logout();
      }
    } finally {
      setIsLoading(false); // Always ensure loading stops
    }
  };

  const login = async () => {
    try {
      console.log('AuthContext: Starting login process');
      
      // Clear any existing tokens and state to ensure a fresh start
      localStorage.removeItem('bungie_token');
      localStorage.removeItem('oauth_state');
      localStorage.removeItem('last_auth_attempt');
      
      // Check for potential redirect loops
      const now = new Date().getTime();
      const lastAttempt = localStorage.getItem('last_auth_attempt');
      
      if (lastAttempt && (now - parseInt(lastAttempt)) < 5000) {
        // If we tried auth within the last 5 seconds, we might be in a loop
        console.warn('AuthContext: Possible redirect loop detected');
        setError('Too many redirects. Please try in an incognito window or clear your browser cache.');
        return;
      }
      
      // Mark this login attempt time
      localStorage.setItem('last_auth_attempt', now.toString());
      
      const response = await axios.get(`${API_URL}/auth/url`);
      console.log('AuthContext: Received response:', response);
      if (response.data && response.data.auth_url) {
        const url = new URL(response.data.auth_url);
        const state = url.searchParams.get('state');
        localStorage.setItem('oauth_state', state);
        
        // Store timestamp for this auth attempt
        localStorage.setItem('auth_redirect_time', now.toString());
        
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
      
      // Check for stale callback (older than 5 minutes)
      const redirectTime = localStorage.getItem('auth_redirect_time');
      const now = new Date().getTime();
      if (redirectTime && (now - parseInt(redirectTime)) > 300000) {
        console.error('AuthContext: Stale callback detected (older than 5 minutes)');
        localStorage.removeItem('oauth_state');
        localStorage.removeItem('auth_redirect_time');
        setError('Authentication session expired. Please try again.');
        throw new Error('Stale authentication callback');
      }
      
      // Get the state parameter from localStorage (sent state)
      const storedState = localStorage.getItem('oauth_state');
      
      console.log('AuthContext: Callback state check:', { 
        receivedState: state, // State received from Bungie
        storedState,       // State we stored before redirect
        stateInLocalStorage: !!localStorage.getItem('oauth_state')
      });
      
      // Verify state parameter
      if (!state || !storedState || state !== storedState) {
         console.error('AuthContext: State mismatch!', { receivedState: state, storedState });
         localStorage.removeItem('oauth_state');
         localStorage.removeItem('auth_redirect_time');
         setError('Security verification failed. Please try again.');
         throw new Error('State parameter mismatch');
      }
      
      // Clear the stored state AFTER verification
      localStorage.removeItem('oauth_state');
      localStorage.removeItem('auth_redirect_time');
      localStorage.removeItem('last_auth_attempt');
      
      console.log('AuthContext: Making callback request to:', `${API_URL}/auth/callback`);
      const response = await axios.post(`${API_URL}/auth/callback`, { code });
      if (response.data && response.data.token_data && response.data.token_data.access_token) {
        localStorage.setItem('bungie_token', response.data.token_data.access_token);
        
        // Also store refresh token if available
        if (response.data.token_data.refresh_token) {
          localStorage.setItem('bungie_refresh_token', response.data.token_data.refresh_token);
        }
        
        // Store token expiry time for future checks
        if (response.data.token_data.expires_in) {
          const expiryTime = new Date().getTime() + (response.data.token_data.expires_in * 1000);
          localStorage.setItem('token_expiry', expiryTime.toString());
        }
        
        setIsAuthenticated(true);
        setError(null);
      } else {
        throw new Error('Invalid token data received');
      }
    } catch (err) {
      console.error('AuthContext: Callback error:', err);
      setError('Authentication failed');
      throw err;
    }
  };

  // Fix the isTokenExpired function
  const isTokenExpired = () => {
    const expiryTime = localStorage.getItem('token_expiry');
    if (!expiryTime) {
      console.log('AuthContext: No expiry time found, assuming token is not expired');
      return false; // Don't assume expired if we don't have an expiry time
    }
    
    const now = new Date().getTime();
    const expired = now > parseInt(expiryTime);
    console.log('AuthContext: Token expiry check:', { 
      now, 
      expiryTime: parseInt(expiryTime), 
      expired,
      timeLeft: Math.round((parseInt(expiryTime) - now) / 1000) + ' seconds'
    });
    
    return expired;
  };

  const logout = () => {
    localStorage.removeItem('bungie_token');
    localStorage.removeItem('bungie_refresh_token');
    localStorage.removeItem('token_expiry');
    localStorage.removeItem('oauth_state');
    localStorage.removeItem('auth_redirect_time');
    localStorage.removeItem('last_auth_attempt');
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