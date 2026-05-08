import { queryClient } from "./queryClient";

class ApiClient {
  private baseUrl = "";
  private token: string | null = null;

  setToken(token: string | null) {
    this.token = token;
  }

  private async request(endpoint: string, options: RequestInit = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    
    const headers = new Headers(options.headers);

    if (!headers.has('Content-Type') && options.body) {
      headers.set('Content-Type', 'application/json');
    }

    if (this.token) {
      headers.set('Authorization', `Bearer ${this.token}`);
    }

    const response = await fetch(url, {
      ...options,
      headers,
      credentials: 'include'
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(error || `HTTP ${response.status}`);
    }

    try {
      // Try to parse as JSON first, as most API responses will be JSON
      return await response.json();
    } catch (e) {
      // If JSON parsing fails, return as text (for non-JSON responses)
      return await response.text();
    }
  }

  async get(endpoint: string) {
    return this.request(endpoint, { method: 'GET' });
  }

  async post(endpoint: string, data?: any, config?: { headers?: Record<string, string> }) {
    const isFormData = typeof FormData !== "undefined" && data instanceof FormData;
    return this.request(endpoint, {
      method: 'POST',
      body: isFormData ? data : (data ? JSON.stringify(data) : undefined),
      headers: isFormData
        ? { ...(config?.headers || {}) }
        : { 'Content-Type': 'application/json', ...(config?.headers || {}) },
    });
  }

  async put(endpoint: string, data?: any) {
    return this.request(endpoint, {
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  async delete(endpoint: string) {
    return this.request(endpoint, { method: 'DELETE' });
  }

  async uploadFile(endpoint: string, file: File, additionalData?: Record<string, any>) {
    const formData = new FormData();
    formData.append('file', file);
    
    if (additionalData) {
      Object.entries(additionalData).forEach(([key, value]) => {
        formData.append(key, typeof value === 'string' ? value : JSON.stringify(value));
      });
    }

    const headers: Record<string, string> = {};
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      method: 'POST',
      headers,
      body: formData,
      credentials: 'include'
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(error || `HTTP ${response.status}`);
    }

    return await response.json();
  }
}

export const api = new ApiClient();

// Auth helpers
export async function login(email: string, password: string) {
  const response = await api.post('/api/auth/login', { email, password });
  const token = response.token;
  api.setToken(token);
  if (typeof window !== 'undefined' && token) {
    localStorage.setItem('auth_token', token);
  }
  return response;
}

export async function register(email: string, username: string, password: string) {
  const response = await api.post('/api/auth/register', { 
    email, 
    username, 
    password, 
    confirmPassword: password 
  });
  const token = response.token;
  api.setToken(token);
  if (typeof window !== 'undefined' && token) {
    localStorage.setItem('auth_token', token);
  }
  return response;
}

export function logout() {
  api.setToken(null);
  if (typeof window !== 'undefined') {
    localStorage.removeItem('auth_token');
  }
  queryClient.clear();
}

// Initialize token from localStorage
if (typeof window !== 'undefined') {
  const savedToken = localStorage.getItem('auth_token');
  if (savedToken) {
    api.setToken(savedToken);
  }
}
