import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { motion, type Variants, type HTMLMotionProps } from "framer-motion"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground hover:bg-primary/80",
        secondary:
          "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
        destructive:
          "border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/80",
        outline: "text-foreground",
        // Glassmorphism variants
        glass: "bg-primary/70 text-primary-foreground backdrop-blur-lg border border-primary/30 hover:bg-primary/80",
        "glass-dark": "bg-primary/30 text-primary-foreground backdrop-blur-lg border border-primary/40 hover:bg-primary/40",
        "neon-glass": "bg-primary/60 text-primary-foreground backdrop-blur-lg border border-primary/20 shadow-[0_0_10px_rgba(0,191,255,0.30)] hover:bg-primary/70",
        subtle: "bg-muted/50 text-muted-foreground hover:bg-muted/60",
        "outline-glass": "border border-input/30 bg-background/70 backdrop-blur-lg text-muted-foreground hover:bg-muted/60",
        elevated: "shadow-lg",
        floating: "shadow-xl",
      },
      size: {
        xs: "h-5 px-2 py-0.5 text-xs",
        sm: "h-6 px-2.5 py-0.5 text-sm",
        default: "h-7 px-3 py-0.5 text-sm",
        lg: "h-8 px-3.5 py-0.5 text-base",
        xl: "h-9 px-4 py-0.5 text-lg",
      },
      state: {
        default: "",
        loading: "animate-pulse opacity-75",
        error: "border-destructive/50 bg-destructive/5 text-destructive/50",
        success: "border-success/50 bg-success/5 text-success/50",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
      state: "default",
    },
  }
)

const badgeAnimations: Variants = {
  initial: {
    scale: 0.9,
    opacity: 0,
  },
  animate: {
    scale: 1,
    opacity: 1,
    transition: {
      type: "spring",
      stiffness: 300,
      damping: 20,
    },
  },
  hover: {
    scale: 1.05,
    transition: {
      type: "spring",
      stiffness: 300,
      damping: 20,
    },
  },
  press: {
    scale: 0.95,
    transition: {
      type: "spring",
      stiffness: 500,
      damping: 20,
    },
  },
  pulse: {
    animation: "pulse 2s infinite",
  },
}

export interface EnhancedBadgeProps
  extends Omit<HTMLMotionProps<"div">, 'variants' | keyof VariantProps<typeof badgeVariants>>,
    VariantProps<typeof badgeVariants> {
  variant?: "default" | "secondary" | "destructive" | "outline" | "glass" | "glass-dark" | "neon-glass" | "subtle" | "outline-glass" | "elevated" | "floating"
  size?: "xs" | "sm" | "default" | "lg" | "xl"
  state?: "default" | "loading" | "error" | "success"
}

const EnhancedBadge = React.forwardRef<
  HTMLDivElement,
  EnhancedBadgeProps
>(({ className, variant, size, state, ...props }, ref) => {
  const baseClasses = cn(
    badgeVariants({ variant, size, state, className })
  )

  return (
    <motion.div
      ref={ref}
      className={baseClasses}
      variants={badgeAnimations}
      initial="initial"
      animate="animate"
      whileTap="press"
      whileHover="hover"
      {...props}
    />
  )
})

EnhancedBadge.displayName = "EnhancedBadge"

export { EnhancedBadge, badgeVariants }