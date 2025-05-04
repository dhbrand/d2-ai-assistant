import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';

const API_URL = 'https://localhost:8000'; // Use HTTPS and port 8000
const MAX_AUTH_RETRIES = 3;
const RETRY_DELAY_MS = 3000; // 3 seconds

// Configure axios to handle HTTPS requests
// axios.defaults.httpsAgent = { // This setup might be Node-specific
//   rejectUnauthorized: false // Note: Only use this in development
// };
// For browsers, certificates are typically handled by the browser itself or mkcert

const AuthContext = createContext(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

// Define the shape of the context value
// interface AuthContextType { // If using TypeScript
//   isAuthenticated: boolean;
//   isLoading: boolean;
//   error: string | null;
//   token: string | null; // Expose token
//   login: () => Promise<void>;
//   logout: () => void;
//   handleCallback: (code: string, state: string) => Promise<void>;
// }


export const AuthProvider = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem('bungie_token')); // Initialize token from localStorage
  const [retryCount, setRetryCount] = useState(0); // State for retries - remove if using direct parameter passing
  const isCheckingAuth = useRef(false); // Ref to prevent multiple concurrent checks


  // Function to check if token expiry stored in localStorage is past
  const isTokenExpired = useCallback(() => {
    console.log('AuthContext: isTokenExpired check started.');
    const expiryTime = localStorage.getItem('token_expiry');
    if (!expiryTime) {
      console.log('AuthContext [isTokenExpired]: No expiry time found in localStorage, assuming not expired (will verify).');
      return false; // If no expiry stored, rely on backend verification
    }
    const now = new Date().getTime();
    const expiryTimestamp = parseInt(expiryTime, 10);
    const expired = now >= expiryTimestamp;
    console.log('AuthContext [isTokenExpired]: Expiry check details:', {
        now,
        expiryTimestamp,
        expired,
        timeLeft: expired ? 'Expired' : `${Math.round((expiryTimestamp - now) / 1000)} seconds`
    });
    return expired;
  }, []); // No dependencies needed


  const logout = useCallback(() => {
    console.log("AuthContext: Logging out.");
    localStorage.removeItem('bungie_token');
    localStorage.removeItem('oauth_state');
    localStorage.removeItem('token_expiry');
    localStorage.removeItem('last_auth_attempt');
    localStorage.removeItem('auth_redirect_time');
    setIsAuthenticated(false);
    setToken(null); // Clear token state
    setError(null);
    // setRetryCount(0); // Reset retries if using state for it
    isCheckingAuth.current = false; // Allow checks again
    // No need to redirect here, handled by PrivateRoute
  }, []); // Include dependencies if it uses state/props


  // Memoize checkAuthStatus to prevent unnecessary calls from useEffect
  const checkAuthStatus = useCallback(async (currentRetry = 0) => {
    // Prevent multiple concurrent checks
    if (isCheckingAuth.current && currentRetry === 0) {
      console.log("AuthContext: Already checking auth status, skipping redundant call.");
      return;
    }
    isCheckingAuth.current = true; // Mark as checking

    // Reset error only on the first attempt of a sequence
    if (currentRetry === 0) {
        setError(null);
    }

    setIsLoading(true);
    console.log(`AuthContext: checkAuthStatus started (Attempt ${currentRetry + 1}).`);

    const currentToken = localStorage.getItem('bungie_token'); // Check localStorage directly

    if (!currentToken) {
      console.log('AuthContext [checkAuthStatus]: No token found in localStorage.');
      // If logout hasn't already cleared state, do it now
      if (isAuthenticated || token) {
          logout();
      }
      setIsLoading(false); // Finished this check sequence
      isCheckingAuth.current = false;
      return;
    }
    console.log('AuthContext [checkAuthStatus]: Token found in localStorage.');

    // Check expiry using memoized function
    if (isTokenExpired()) {
      console.log('AuthContext [checkAuthStatus]: Token deemed expired by frontend check.');
      logout(); // Logout clears state and localStorage
      setIsLoading(false);
      isCheckingAuth.current = false;
      return;
    }
    console.log('AuthContext [checkAuthStatus]: Token not expired by frontend, verifying with backend...');

    try {
      const response = await axios.get(`${API_URL}/auth/verify`, {
        headers: { Authorization: `Bearer ${currentToken}` }
      });
      console.log('AuthContext [checkAuthStatus]: Backend verification response:', response.status, response.data);

      if (response.data && response.data.status === 'valid') {
        console.log('AuthContext [checkAuthStatus]: Backend verification successful.');
        setIsAuthenticated(true);
        setToken(currentToken); // Ensure state reflects the valid token from localStorage
        setError(null);
        // Reset retry logic on success
        isCheckingAuth.current = false; // Done checking
        setIsLoading(false); // Success, finished loading
      } else {
        console.log('AuthContext [checkAuthStatus]: Backend verification failed (invalid response). Logging out.');
        logout();
        isCheckingAuth.current = false;
        setIsLoading(false);
      }
    } catch (err) {
      console.error(`AuthContext [checkAuthStatus]: Error during attempt ${currentRetry + 1}:`, err);
      let shouldStopLoading = true; // Assume we stop loading unless a retry is scheduled
      let shouldStopChecking = true; // Assume we stop the check sequence

      if (err.response) {
        // Handle specific backend errors
        if (err.response.status === 401 || err.response.status === 403) {
          console.log('AuthContext [checkAuthStatus]: Received 401/403, logging out.');
          logout();
        } else if (err.response.status === 503) {
          // Handle retries for 503 (Service Unavailable)
          if (currentRetry < MAX_AUTH_RETRIES - 1) {
            const nextRetry = currentRetry + 1;
            setError(`Unable to verify session (Bungie API unavailable?). Retrying ${nextRetry}/${MAX_AUTH_RETRIES}...`);
            console.log(`AuthContext [checkAuthStatus]: Received 503, scheduling retry ${nextRetry} in ${RETRY_DELAY_MS}ms.`);
            // Schedule the next attempt
             setTimeout(() => checkAuthStatus(nextRetry), RETRY_DELAY_MS);
             shouldStopLoading = false; // Don't stop loading, retry scheduled
             shouldStopChecking = false; // Don't stop checking sequence, retry scheduled
          } else {
            console.log(`AuthContext [checkAuthStatus]: Received 503, max retries (${MAX_AUTH_RETRIES}) reached. Logging out.`);
            setError(`Failed to verify session after ${MAX_AUTH_RETRIES} attempts (Bungie API unavailable?). Please try logging in again.`);
            logout();
          }
        } else {
           // Handle other unexpected backend errors
           console.log(`AuthContext [checkAuthStatus]: Received unexpected backend error: ${err.response.status}. Logging out.`);
           setError(`An unexpected server error (${err.response.status}) occurred during verification.`);
           logout();
        }
      } else {
        // Handle network errors (request didn't reach server)
        console.log('AuthContext [checkAuthStatus]: Network error during verification. Cannot verify status.');
        setError('Network error trying to verify session. Please check connection.');
        // Keep current auth state on network error? Or logout? Logout is safer.
        logout();
      }

      // Update state based on decisions above
      if (shouldStopChecking) {
          isCheckingAuth.current = false;
      }
       if (shouldStopLoading) {
          setIsLoading(false);
           console.log('AuthContext: checkAuthStatus sequence finished (isLoading set to false).');
       } else {
            console.log('AuthContext: checkAuthStatus attempt finished, but retrying...');
       }
    }
    // Removed finally block, handling state updates within catch/try success branches
  }, [isTokenExpired, logout, token, isAuthenticated]); // Added token/isAuthenticated dependencies


  // Effect runs on initial mount to check auth status
  useEffect(() => {
    console.log("AuthContext: Initial mount useEffect running checkAuthStatus.");
    checkAuthStatus(0); // Start the check sequence
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Run only once on mount


  const login = useCallback(async () => {
    // (Keep existing login logic, ensure it clears state/localStorage properly before redirect)
    try {
      console.log('AuthContext: Starting login process');
      // Clear existing state *before* getting URL
      logout(); // Use logout function to ensure cleanup
      setIsLoading(true); // Set loading true during redirect preparation

      // Anti-redirect loop check
      const now = new Date().getTime();
      const lastAttempt = localStorage.getItem('last_auth_attempt');
      if (lastAttempt && (now - parseInt(lastAttempt)) < 5000) {
        console.warn('AuthContext: Possible redirect loop detected');
        setError('Too many redirects. Please try clearing cache or using incognito.');
        setIsLoading(false);
        return;
      }
      localStorage.setItem('last_auth_attempt', now.toString());

      const response = await axios.get(`${API_URL}/auth/url`);
      console.log('AuthContext: Received auth URL response:', response);
      if (response.data && response.data.auth_url) {
        const url = new URL(response.data.auth_url);
        const state = url.searchParams.get('state');
        if (state) {
             localStorage.setItem('oauth_state', state);
             localStorage.setItem('auth_redirect_time', now.toString());
             console.log('AuthContext: Redirecting to Bungie OAuth page:', response.data.auth_url);
             window.location.href = response.data.auth_url;
             // Don't set loading false, page will redirect
        } else {
             console.error('AuthContext: Auth URL received from backend is missing state parameter.');
             throw new Error('Invalid auth_url received (missing state)');
        }
      } else {
        console.error('AuthContext: Invalid response data from /auth/url:', response.data);
        throw new Error('No auth_url received from server');
      }
    } catch (err) {
      console.error('AuthContext: Login error:', err);
      setError(`Failed to initiate authentication: ${err.message || 'Unknown error'}`);
      setIsLoading(false); // Ensure loading is false on error
      // Don't re-throw, allow component to handle the error state
    }
  }, [logout]); // Include logout in dependency array


  const handleCallback = useCallback(async (code, state) => {
    // (Keep existing handleCallback logic, ensure it sets token state on success)
     setIsLoading(true); // Ensure loading is true during callback processing
     console.log('AuthContext: Handling callback with code and state');

    try {
      // Stale callback check
      const redirectTime = localStorage.getItem('auth_redirect_time');
      const now = new Date().getTime();
      if (redirectTime && (now - parseInt(redirectTime)) > 300000) { // 5 minutes
        console.error('AuthContext: Stale callback detected.');
        throw new Error('Authentication session expired.');
      }

      // State check
      const storedState = localStorage.getItem('oauth_state');
      console.log('AuthContext: Callback state check:', { receivedState: state, storedState });
      if (!state || !storedState || state !== storedState) {
         console.error('AuthContext: State mismatch!');
         throw new Error('Security verification failed (state mismatch).');
      }

       // Clear transient items *after* verification
      localStorage.removeItem('oauth_state');
      localStorage.removeItem('auth_redirect_time');
      localStorage.removeItem('last_auth_attempt');

      console.log('AuthContext: Making callback request to backend...');
      const response = await axios.post(`${API_URL}/auth/callback`, { code });

      if (response.data && response.data.token_data && response.data.token_data.access_token) {
        const receivedToken = response.data.token_data.access_token;
        localStorage.setItem('bungie_token', receivedToken);
        setToken(receivedToken); // Update state

        if (response.data.token_data.expires_in) {
          const expiryTime = new Date().getTime() + (response.data.token_data.expires_in * 1000);
          localStorage.setItem('token_expiry', expiryTime.toString());
        } else {
             localStorage.removeItem('token_expiry'); // Clear expiry if not provided
        }

        setIsAuthenticated(true);
        setError(null);
        console.log("AuthContext: Callback successful, user authenticated.");
      } else {
         console.error('AuthContext: Invalid token data received from callback:', response.data);
        throw new Error('Invalid token data received from server.');
      }
    } catch (err) {
      console.error('AuthContext: Callback error:', err);
      setError(`Authentication failed: ${err.message || 'Unknown error'}`);
      logout(); // Ensure logout on callback failure
    } finally {
        setIsLoading(false); // Ensure loading is false after processing
    }
  }, [logout]); // Include logout dependency


  // const contextValue: AuthContextType = { // If using TypeScript
  const contextValue = {
    isAuthenticated,
    isLoading,
    error,
    token, // Provide token in context
    login,
    logout,
    handleCallback,
  };

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  );
}; 