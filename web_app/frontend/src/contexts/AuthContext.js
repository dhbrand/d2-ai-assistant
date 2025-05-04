import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';

const API_URL = 'https://localhost:8000'; // Use HTTPS and port 8000
const MAX_AUTH_RETRIES = 3;
const RETRY_DELAY_MS = 3000; // 3 seconds

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
  const [retryCount, setRetryCount] = useState(0); // State for retries
  const isRetrying = useRef(false); // Ref to prevent multiple retry loops

  // Memoize checkAuthStatus to prevent unnecessary calls from useEffect
  const checkAuthStatus = useCallback(async () => {
    if (isRetrying.current && retryCount === 0) {
      console.log("AuthContext: Already checking/retrying, skipping redundant call.");
      return;
    }
    if (retryCount === 0) {
        setError(null); 
        isRetrying.current = true; 
    }

    setIsLoading(true); 
    console.log(`AuthContext: checkAuthStatus started (Attempt ${retryCount + 1}).`);

    try {
      const token = localStorage.getItem('bungie_token');
      if (!token) {
        console.log('AuthContext [checkAuthStatus]: No token found.');
        setIsAuthenticated(false);
        setRetryCount(0);
        isRetrying.current = false;
        // No need to set isLoading false here, finally block handles it
        return;
      }
      console.log('AuthContext [checkAuthStatus]: Token found.');

      if (isTokenExpired()) {
        console.log('AuthContext [checkAuthStatus]: Token deemed expired by frontend.');
        logout(); 
        isRetrying.current = false;
         // No need to set isLoading false here, finally block handles it
        return;
      }
      console.log('AuthContext [checkAuthStatus]: Token not expired by frontend, verifying with backend...');

      const response = await axios.get(`${API_URL}/auth/verify`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      console.log('AuthContext [checkAuthStatus]: Backend verification response:', response.status, response.data);

      if (response.data && response.data.status === 'valid') {
        console.log('AuthContext [checkAuthStatus]: Backend verification successful.');
        setIsAuthenticated(true);
        setError(null);
        setRetryCount(0); 
        isRetrying.current = false; // Success, stop retrying flag
      } else {
        console.log('AuthContext [checkAuthStatus]: Backend verification failed (unexpected response format).', response.data);
        logout();
        isRetrying.current = false;
      }
    } catch (err) {
      console.error(`AuthContext [checkAuthStatus]: Error during attempt ${retryCount + 1}:`, err);
      if (err.response) {
        if (err.response.status === 401 || err.response.status === 403) {
          console.log('AuthContext [checkAuthStatus]: Received 401/403, logging out.');
          logout();
          isRetrying.current = false;
        } else if (err.response.status === 503) {
          if (retryCount < MAX_AUTH_RETRIES - 1) {
            const nextRetryCount = retryCount + 1;
            setRetryCount(nextRetryCount);
            setError(`Unable to verify session (Bungie API unavailable?). Retrying ${nextRetryCount}/${MAX_AUTH_RETRIES}...`);
            console.log(`AuthContext [checkAuthStatus]: Received 503, scheduling retry ${nextRetryCount} in ${RETRY_DELAY_MS}ms.`);
            setTimeout(() => checkAuthStatus(), RETRY_DELAY_MS);
            return; // Exit catch block, isLoading stays true via finally logic
          } else {
            console.log(`AuthContext [checkAuthStatus]: Received 503, max retries (${MAX_AUTH_RETRIES}) reached, logging out.`);
            setError(`Failed to verify session after ${MAX_AUTH_RETRIES} attempts (Bungie API unavailable?). Please try logging in again.`);
            logout();
            isRetrying.current = false;
          }
        } else {
           console.log(`AuthContext [checkAuthStatus]: Received unexpected backend error: ${err.response.status}. Logging out.`);
           setError(`An unexpected server error (${err.response.status}) occurred during verification.`);
           logout();
           isRetrying.current = false;
        }
      } else {
        console.log('AuthContext [checkAuthStatus]: Network error during verification. Keeping current auth state.');
        setError('Network error trying to verify session. Please check your connection.');
        setRetryCount(0); 
        isRetrying.current = false;
      }
    } finally {
      // Set loading false only if we are truly finished (success, fatal error, or max retries)
      // If a retry is scheduled, isRetrying.current should still be true, skip setting loading false.
      if (!isRetrying.current || retryCount >= MAX_AUTH_RETRIES-1) { // check flags correctly
          setIsLoading(false);
          console.log('AuthContext: checkAuthStatus finished (isLoading set to false).');
          isRetrying.current = false; // Ensure it's reset after final attempt
      } else if (isRetrying.current && retryCount < MAX_AUTH_RETRIES -1) {
           console.log('AuthContext: checkAuthStatus attempt finished, but retrying...');
      }
    }
  }, [retryCount]); // Dependency for useCallback

  useEffect(() => {
    checkAuthStatus();
    // Call the memoized version on initial mount
  }, [checkAuthStatus]); // Dependency ensures it runs once with the correct function reference

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

  const isTokenExpired = () => {
    console.log('AuthContext: isTokenExpired check started.');
    const expiryTime = localStorage.getItem('token_expiry');
    if (!expiryTime) {
      console.log('AuthContext [isTokenExpired]: No expiry time found in localStorage, assuming not expired.');
      return false;
    }
    console.log(`AuthContext [isTokenExpired]: Found expiry time string: '${expiryTime}'`);
    
    const now = new Date().getTime();
    const expiryTimestamp = parseInt(expiryTime); 

    if (isNaN(expiryTimestamp)) {
      console.error('AuthContext [isTokenExpired]: Invalid expiry time format in localStorage, cannot parse to integer:', expiryTime);
      return true;
    }

    const expired = now > expiryTimestamp;
    console.log('AuthContext [isTokenExpired]: Expiry check details:', {
      now,
      expiryTimestamp,
      expired,
      timeLeft: Math.round((expiryTimestamp - now) / 1000) + ' seconds'
    });
    
    return expired;
  };

  const logout = () => {
    console.log("AuthContext: logout called.");
    localStorage.removeItem('bungie_token');
    localStorage.removeItem('bungie_refresh_token');
    localStorage.removeItem('token_expiry');
    localStorage.removeItem('oauth_state');
    localStorage.removeItem('auth_redirect_time');
    localStorage.removeItem('last_auth_attempt');
    setIsAuthenticated(false);
    setRetryCount(0); // Reset retries on logout
    setError(null); // Clear errors on logout
    isRetrying.current = false; 
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