import * as React from "react";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";

export interface ThemeProviderProps {
  children: React.ReactNode;
  defaultTheme?: "light" | "dark" | "system";
}

// Create context outside the component so it can be used by useTheme hook
const ThemeContext = React.createContext<{
  theme: "light" | "dark";
  toggleTheme: () => void;
  highContrast: boolean;
  toggleHighContrast: () => void;
} | undefined>(undefined);

// Define the light and dark theme values based on our CSS variables
const lightTheme = {
  "--background": "hsl(210 20% 96%)",
  "--foreground": "hsl(222 47% 11%)",
  "--card": "hsl(0 0% 100%)",
  "--card-foreground": "hsl(222 47% 11%)",
  "--popover": "hsl(0 0% 100%)",
  "--popover-foreground": "hsl(222 47% 11%)",
  "--primary": "hsl(195 100% 40%)",
  "--primary-foreground": "hsl(0 0% 100%)",
  "--secondary": "hsl(210 40% 90%)",
  "--secondary-foreground": "hsl(222 47% 11%)",
  "--muted": "hsl(210 40% 93%)",
  "--muted-foreground": "hsl(215 16% 47%)",
  "--accent": "hsl(210 40% 90%)",
  "--accent-foreground": "hsl(195 100% 35%)",
  "--destructive": "hsl(0 84% 60%)",
  "--destructive-foreground": "hsl(0 0% 100%)",
  "--border": "hsl(214 32% 85%)",
  "--input": "hsl(214 32% 91%)",
  "--ring": "hsl(195 100% 40%)",
};

const darkTheme = {
  "--background": "hsl(240 10% 3%)",
  "--foreground": "hsl(200 6.6667% 91%)",
  "--card": "hsl(228 9.8039% 8%)",
  "--card-foreground": "hsl(0 0% 85%)",
  "--popover": "hsl(240 10% 5%)",
  "--popover-foreground": "hsl(200 6.6667% 91%)",
  "--primary": "hsl(195 100% 50%)",
  "--primary-foreground": "hsl(0 0% 0%)",
  "--secondary": "hsl(230 10% 15%)",
  "--secondary-foreground": "hsl(200 6.6667% 91%)",
  "--muted": "hsl(230 10% 10%)",
  "--muted-foreground": "hsl(210 3.3898% 46%)",
  "--accent": "hsl(205 70% 8%)",
  "--accent-foreground": "hsl(195 100% 50%)",
  "--destructive": "hsl(0 100% 60%)",
  "--destructive-foreground": "hsl(0 0% 100%)",
  "--border": "hsl(230 10% 14%)",
  "--input": "hsl(230 12% 12%)",
  "--ring": "hsl(195 100% 50%)",
};

export function ThemeProvider({
  children,
  defaultTheme = "system"
}: ThemeProviderProps) {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    // Check for saved theme preference or use default
    const savedTheme = localStorage.getItem("theme");
    if (savedTheme) {
      return savedTheme as "light" | "dark";
    }

    if (defaultTheme === "system") {
      return window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
    }

    return defaultTheme;
  });

  const [highContrast, setHighContrast] = useState<boolean>(() => {
    const saved = localStorage.getItem("highContrast");
    return saved ? saved === "true" : false;
  });

  useEffect(() => {
    // Save theme preference
    localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(() => {
    // Save high contrast preference
    localStorage.setItem("highContrast", String(highContrast));
  }, [highContrast]);

  useEffect(() => {
    // Listen for system theme changes if defaultTheme is "system"
    if (defaultTheme === "system") {
      const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
      const handleChange = (e: MediaQueryListEvent) => {
        setTheme(e.matches ? "dark" : "light");
      };

      mediaQuery.addEventListener("change", handleChange);
      return () => mediaQuery.removeEventListener("change", handleChange);
    }
  }, [defaultTheme]);

  const toggleTheme = () => {
    setTheme(prevTheme => (prevTheme === "light" ? "dark" : "light"));
  };

  const toggleHighContrast = () => {
    setHighContrast(prev => !prev);
  };

  // Get the style object for the current theme
  const baseThemeStyles = theme === "dark" ? darkTheme : lightTheme;

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, highContrast, toggleHighContrast }}>
      <motion.div
        style={{
          ...baseThemeStyles,
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100vw',
          height: '100vh',
          filter: highContrast ? 'contrast(150%)' : 'none',
        }}
        transition={{ duration: 0.3 }}
      >
        {children}
      </motion.div>
    </ThemeContext.Provider>
  );
}

export const useTheme = () => {
  const context = React.useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
};