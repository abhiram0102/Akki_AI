import * as React from "react"
import { motion, type Variants, type HTMLMotionProps } from "framer-motion"

import { cn } from "@/lib/utils"

const inputAnimations: Variants = {
  initial: {
    borderWidth: "1px",
  },
  focus: {
    borderWidth: "2px",
    transition: {
      borderWidth: {
        type: "spring",
        stiffness: 300,
        damping: 20,
      },
    },
  },
}

export interface ModernInputProps
  extends Omit<HTMLMotionProps<"input">, 'variants' | 'size'> {
  className?: string
  variant?: "default" | "outlined" | "filled" | "underlined"
  size?: "default" | "sm" | "lg"
}

const ModernInput = React.forwardRef<
  HTMLInputElement,
  ModernInputProps
>(({ className, variant = "default", size = "default", ...props }, ref) => {
  const baseClasses = "flex h-9 w-full rounded-md border border-input px-3 py-1 text-base shadow-sm transition-all file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm"

  const variantClasses = {
    default: "bg-background",
    outlined: "bg-transparent",
    filled: "bg-muted/50",
    underlined: "border-b border-b-border rounded-none",
  }

  const sizeClasses = {
    default: "h-9 px-3 py-1 text-base",
    sm: "h-8 px-2 py-0 text-xs",
    lg: "h-10 px-4 py-2 text-lg",
  }

  return (
    <motion.input
      ref={ref}
      type={props.type || "text"}
      className={cn(
        baseClasses,
        variantClasses[variant],
        sizeClasses[size],
        className
      )}
      variants={inputAnimations}
      whileHover={{ borderWidth: "1.5px" }}
      whileFocus="focus"
      {...props}
    />
  )
})

ModernInput.displayName = "ModernInput"

export { ModernInput }