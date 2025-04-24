import { render, screen } from '@testing-library/react';
import App from '../App';

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

describe('App Component', () => {
  test('renders login page when not authenticated', () => {
    render(<App />);
    expect(screen.getByText(/Welcome Guardian/i)).toBeInTheDocument();
  });
}); 