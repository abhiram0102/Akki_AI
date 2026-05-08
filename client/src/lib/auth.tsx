// @refresh reset
import { createContext, useContext, useState, useEffect, type ReactNode } from "react";
import { api, login as apiLogin, register as apiRegister, logout as apiLogout } from "./api";
import { useQuery, useQueryClient } from "@tanstack/react-query";

interface User {
  id: string;
  email: string;
  username: string;
  role: string;
  preferences: any;
  emotionalState: {
    bondLevel: number;
    currentMood: string;
    trustLevel: number;
    personalityTraits: string[];
    preferredCommunicationStyle: string;
  };
  createdAt: string;
  lastActiveAt: string;
}

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, username: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isInitialized, setIsInitialized] = useState(false);
  const queryClient = useQueryClient();

  useEffect(() => {
    const storedToken = localStorage.getItem("auth_token");
    if (storedToken) {
      api.setToken(storedToken);
      setToken(storedToken);
    }
    setIsInitialized(true);
  }, []);

  const { data: userData, isLoading: isLoadingUser, refetch: refetchUser } = useQuery<User>({
    queryKey: ["/api/protected/profile"],
    queryFn: () => api.get("/api/protected/profile"),
    enabled: isInitialized && !!token,
    retry: (failureCount, error: any) => {
      if (error?.message?.includes("401")) return false;
      return failureCount < 2;
    },
    staleTime: 30000,
  });

  useEffect(() => {
    if (userData) {
      setUser(userData);
    } else if (isInitialized && !isLoadingUser && !token) {
      setUser(null);
    }
  }, [userData, isInitialized, isLoadingUser, token]);

  const login = async (email: string, password: string) => {
    const response = await apiLogin(email, password);
    setToken(response.token);
    setUser(response.user);
    await queryClient.invalidateQueries();
  };

  const register = async (email: string, username: string, password: string) => {
    const response = await apiRegister(email, username, password);
    setToken(response.token);
    setUser(response.user);
    await queryClient.invalidateQueries();
  };

  const logout = () => {
    apiLogout();
    setUser(null);
    setToken(null);
    queryClient.clear();
  };

  const refreshUser = () => refetchUser();

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading: !isInitialized || (isLoadingUser && !!token),
        login,
        register,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
