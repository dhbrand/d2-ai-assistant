import { render, screen } from '@testing-library/react';
import React from 'react';
import App from '../App';
import { ThemeProvider, createTheme } from '@mui/material/styles';

// Mock axios
jest.mock('axios', () => ({
  default: {
    get: jest.fn(() => Promise.resolve({ data: {} })),
    post: jest.fn(() => Promise.resolve({ data: {} })),
  },
}));

// Mock the AuthContext
jest.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    isAuthenticated: false,
    isLoading: false,
    error: null,
    login: jest.fn(),
    logout: jest.fn(),
  }),
  AuthProvider: ({ children }) => children,
}));

// Mock react-router-dom
jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  BrowserRouter: ({ children }) => <div>{children}</div>,
}));

const theme = createTheme();

const AllTheProviders = ({ children }) => {
  return (
    <ThemeProvider theme={theme}>
      {children}
    </ThemeProvider>
  );
};

describe('App Component', () => {
  test('renders without crashing', () => {
    render(<App />, { wrapper: AllTheProviders });
    expect(document.body).toBeInTheDocument();
  });
}); 