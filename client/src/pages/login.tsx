import { useState, useEffect } from "react";
import { useLocation } from "wouter";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/lib/auth";

function ClientOnlyLogin() {
  const [, setLocation] = useLocation();
  const { login, register } = useAuth();
  const { toast } = useToast();
  const [isRegister, setIsRegister] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [formData, setFormData] = useState({
    email: "",
    username: "",
    password: "",
    confirmPassword: ""
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      if (isRegister) {
        if (formData.password !== formData.confirmPassword) {
          throw new Error("Passwords don't match");
        }
        await register(formData.email, formData.username, formData.password);
        toast({
          title: "Registration successful",
          description: "Welcome to AKKI AI!"
        });
      } else {
        await login(formData.email, formData.password);
        toast({
          title: "Login successful", 
          description: "Welcome back!"
        });
      }
      setLocation("/");
    } catch (error) {
      toast({
        title: isRegister ? "Registration failed" : "Login failed",
        description: error instanceof Error ? error.message : "An error occurred",
        variant: "destructive"
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen terminal-bg flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-gradient-to-br from-cyber-blue/5 via-transparent to-cyber-green/5" />
      <Card className="w-full max-w-md glass border-white/20 relative z-10" data-testid="login-card">
        <CardHeader className="text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gradient-to-br from-cyber-blue to-cyber-green flex items-center justify-center">
            <i className="fas fa-brain text-white text-2xl" />
          </div>
          <CardTitle className="text-2xl font-bold text-white font-display tracking-wider">
            AKKI AI
          </CardTitle>
          <p className="text-cyan-400 text-xs font-mono tracking-widest uppercase">Autonomous Cybersecurity OS</p>
        </CardHeader>
        
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <Label htmlFor="email" className="text-white">Email</Label>
              <Input
                id="email"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                className="bg-space-gray/50 border-white/20 text-white"
                required
                data-testid="input-email"
              />
            </div>
            
            {isRegister && (
              <div>
                <Label htmlFor="username" className="text-white">Username</Label>
                <Input
                  id="username"
                  type="text"
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  className="bg-space-gray/50 border-white/20 text-white"
                  required
                  data-testid="input-username"
                />
              </div>
            )}
            
            <div>
              <Label htmlFor="password" className="text-white">Password</Label>
              <Input
                id="password"
                type="password"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                className="bg-space-gray/50 border-white/20 text-white"
                required
                data-testid="input-password"
              />
            </div>
            
            {isRegister && (
              <div>
                <Label htmlFor="confirmPassword" className="text-white">Confirm Password</Label>
                <Input
                  id="confirmPassword"
                  type="password"
                  value={formData.confirmPassword}
                  onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
                  className="bg-space-gray/50 border-white/20 text-white"
                  required
                  data-testid="input-confirm-password"
                />
              </div>
            )}
            
            <Button
              type="submit"
              className="w-full bg-gradient-to-r from-cyber-blue to-cyber-green text-black font-medium hover:shadow-lg hover:shadow-cyber-blue/25 transition-all"
              disabled={isLoading}
              data-testid="button-submit"
            >
              {isLoading ? "Loading..." : isRegister ? "Register" : "Login"}
            </Button>
          </form>
          
          <div className="mt-6 text-center">
            <button
              type="button"
              onClick={() => setIsRegister(!isRegister)}
              className="text-cyber-blue hover:text-cyber-green transition-colors"
              data-testid="button-toggle-mode"
            >
              {isRegister ? "Already have an account? Login" : "Need an account? Register"}
            </button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default function Login() {
  const [isClient, setIsClient] = useState(false);

  useEffect(() => {
    setIsClient(true);
  }, []);

  return isClient ? <ClientOnlyLogin /> : null;
}
