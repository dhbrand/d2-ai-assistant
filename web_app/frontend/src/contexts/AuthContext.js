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
    // Check for JWT expiry
    const expiryTime = localStorage.getItem('jwt_expiry'); 
    if (!expiryTime) {
      // If no expiry stored, assume expired for JWT (as it SHOULD have an expiry)
      console.log('AuthContext [isTokenExpired]: No JWT expiry time found in localStorage, assuming expired.');
      return true; 
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
    localStorage.removeItem('bungie_token'); // Keep removing old one just in case
    localStorage.removeItem('token_expiry'); // Keep removing old one just in case
    localStorage.removeItem('app_jwt'); // Remove JWT
    localStorage.removeItem('jwt_expiry'); // Remove JWT expiry
    localStorage.removeItem('oauth_state');
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

    // Check for JWT in localStorage
    const currentToken = localStorage.getItem('app_jwt'); 

    if (!currentToken) {
      console.log('AuthContext [checkAuthStatus]: No JWT found in localStorage.');
      // If logout hasn't already cleared state, do it now
      if (isAuthenticated || token) {
          logout();
      }
      setIsLoading(false); // Finished this check sequence
      isCheckingAuth.current = false;
      return;
    }
    console.log('AuthContext [checkAuthStatus]: JWT found in localStorage.');

    // Check expiry using memoized function (now checks jwt_expiry)
    if (isTokenExpired()) {
      console.log('AuthContext [checkAuthStatus]: JWT deemed expired by frontend check.');
      logout(); // Logout clears state and localStorage
      setIsLoading(false);
      isCheckingAuth.current = false;
      return;
    }
    console.log('AuthContext [checkAuthStatus]: JWT not expired by frontend, considering user authenticated.');

    // If JWT exists and is not expired locally, set authenticated state
    console.log('AuthContext [checkAuthStatus]: Setting isAuthenticated = true based on local JWT.');
    setIsAuthenticated(true);
    setToken(currentToken); // Ensure token state matches localStorage
    setError(null);
    setIsLoading(false);
    isCheckingAuth.current = false;

  }, [isTokenExpired, logout]); // Dependencies: isTokenExpired, logout


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

      // -- Updated logic for JWT response --
      if (response.data && response.data.access_token && response.data.token_type === 'bearer') {
        const receivedJwt = response.data.access_token;
        localStorage.setItem('app_jwt', receivedJwt);
        setToken(receivedJwt); // Update state with JWT

        if (response.data.expires_in) {
          // Calculate expiry based on current time + expires_in (seconds)
          const expiryTimestamp = new Date().getTime() + (response.data.expires_in * 1000);
          localStorage.setItem('jwt_expiry', expiryTimestamp.toString());
          console.log(`AuthContext: Stored JWT expiry: ${new Date(expiryTimestamp)}`);
        } else {
             console.warn('AuthContext: JWT received but no expires_in value provided by backend.');
             localStorage.removeItem('jwt_expiry'); // Clear expiry if not provided
        }

        setIsAuthenticated(true);
        setError(null);
        console.log("AuthContext: Callback successful, user authenticated with JWT.");
      } else {
         console.error('AuthContext: Invalid JWT data received from callback:', response.data);
        throw new Error('Invalid token data received from server.');
      }
      // -- End updated logic --

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