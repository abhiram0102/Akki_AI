import * as React from "react"
import { motion, type Variants, type HTMLMotionProps } from "framer-motion"

import { cn } from "@/lib/utils"

const inputAnimations: Variants = {
  initial: { opacity: 0, y: -4 },
  animate: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 300, damping: 20 } },
  focus: { scale: 1.01 },
  error: { x: [-2, 2, -2, 2, 0], transition: { duration: 0.4 } },
  success: { scale: 1.02, transition: { duration: 0.2 } },
}

export interface EnhancedModernInputProps
  extends Omit<HTMLMotionProps<"input">, 'variants' | 'size' | 'prefix'> {
  className?: string
  variant?: "default" | "outlined" | "filled" | "underlined" | "glass" | "glass-dark" | "neon-glass" | "neon-outline"
  size?: "default" | "sm" | "lg" | "xs" | "xl"
  state?: "default" | "focus" | "error" | "success" | "disabled"
  prefix?: React.ReactNode
  suffix?: React.ReactNode
}

const EnhancedModernInput = React.forwardRef<
  HTMLInputElement,
  EnhancedModernInputProps
>(({ className, variant = "default", size = "default", state = "default", prefix, suffix, ...props }, ref) => {
  const baseClasses = "flex h-9 w-full rounded-md border border-input px-3 py-1 text-base shadow-sm transition-all file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm"

  const variantClasses = {
    default: "bg-background",
    outlined: "bg-transparent",
    filled: "bg-muted/50",
    underlined: "border-b border-b-border rounded-none",
    // Glassmorphism variants
    glass: "bg-background/70 backdrop-blur-lg border border-input/30",
    "glass-dark": "bg-background/30 backdrop-blur-lg border border-input/40",
    "neon-glass": "bg-background/60 backdrop-blur-lg border border-input/20 shadow-[0_0_10px_rgba(0,191,255,0.30)]",
    "neon-outline": "border border-input/20 bg-transparent text-input-foreground shadow-[0_0_5px_rgba(0,191,255,0.20)]",
  }

  const sizeClasses = {
    default: "h-9 px-3 py-1 text-base",
    sm: "h-8 px-2 py-0 text-xs",
    lg: "h-10 px-4 py-2 text-lg",
    xs: "h-7 px-2 py-0 text-xs",
    xl: "h-11 px-4 py-2 text-lg",
  }

  const stateClasses = {
    default: "",
    focus: "border-primary/50 ring-1 ring-primary/20",
    error: "border-destructive/50 bg-destructive/5",
    success: "border-success/50 bg-success/5",
    disabled: "opacity-50 cursor-not-allowed",
  }

  return (
    <motion.div
      className="relative"
      variants={inputAnimations}
      initial="initial"
      animate={state}
    >
      {prefix && (
        <div className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none">
          {prefix}
        </div>
      )}
      <motion.input
        ref={ref}
        type={props.type || "text"}
        className={cn(
          baseClasses,
          variantClasses[variant],
          sizeClasses[size],
          stateClasses[state],
          className
        )}
        {...props}
      />
      {suffix && (
        <div className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none">
          {suffix}
        </div>
      )}
      {state === "error" && (
        <div className="absolute bottom-0 left-0 right-0 -mb-2 text-destructive text-xs pointer-events-none">
          {/* Error message would typically come from form validation */}
        </div>
      )}
    </motion.div>
  )
})

EnhancedModernInput.displayName = "EnhancedModernInput"

export { EnhancedModernInput }