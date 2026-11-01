import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { motion, type Variants, type HTMLMotionProps } from "framer-motion"

import { cn } from "@/lib/utils"

const cardVariants = cva(
  "rounded-xl border bg-card text-card-foreground shadow transition-all group",
  {
    variants: {
      variant: {
        default: "",
        glass: "bg-card/70 backdrop-blur-lg border-border/30",
        "glass-dark": "bg-card/30 backdrop-blur-lg border-border/40",
        "neon-glass": "bg-card/60 backdrop-blur-lg border-border/20 shadow-[0_0_15px_rgba(0,191,255,0.50)]",
        "neon-glass-dark": "bg-card/40 backdrop-blur-lg border-border/30 shadow-[0_0_15px_rgba(0,191,255,0.30)]",
        elevated: "shadow-lg",
        floating: "shadow-xl",
        outline: "border border-input bg-background",
        subtle: "bg-muted/50 border-transparent",
      },
      state: {
        default: "",
        loading: "opacity-75 pointer-events-none",
        error: "border-destructive/50 bg-destructive/5",
        success: "border-success/50 bg-success/5",
        empty: "border-dashed border-muted/40 bg-muted/10",
      },
      size: {
        default: "",
        sm: "rounded-lg px-4 py-3",
        lg: "rounded-2xl px-6 py-4",
      },
    },
    defaultVariants: {
      variant: "default",
      state: "default",
      size: "default",
    },
  }
)

const cardAnimations: Variants = {
  initial: {
    scale: 0.98,
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
    scale: 1.02,
    transition: {
      type: "spring",
      stiffness: 300,
      damping: 20,
    },
  },
  press: {
    scale: 0.98,
    transition: {
      type: "spring",
      stiffness: 500,
      damping: 20,
    },
  },
  exit: {
    scale: 0.95,
    opacity: 0,
    transition: {
      type: "spring",
      stiffness: 300,
      damping: 20,
    },
  },
}

interface EnhancedModernCardProps
  extends Omit<HTMLMotionProps<"div">, 'variants' | keyof VariantProps<typeof cardVariants>>,
    VariantProps<typeof cardVariants> {
  children: React.ReactNode
  hoverEffect?: boolean
  loadingText?: string
  errorText?: string
  emptyText?: string
  successText?: string
  variant?: "default" | "glass" | "glass-dark" | "neon-glass" | "neon-glass-dark" | "elevated" | "floating" | "outline" | "subtle"
  state?: "default" | "loading" | "error" | "success" | "empty"
  size?: "default" | "sm" | "lg"
}

const EnhancedModernCard = React.forwardRef<
  HTMLDivElement,
  EnhancedModernCardProps
>(({ className, variant = "default", state = "default", size = "default", hoverEffect = true, children, loadingText, errorText, emptyText, successText, ...props }, ref) => {
  const baseClasses = cn(
    cardVariants({ variant, state, size, className })
  )

  return (
    <motion.div
      ref={ref}
      className={baseClasses}
      variants={cardAnimations}
      initial="initial"
      animate="animate"
      whileTap={hoverEffect ? "press" : undefined}
      whileHover={hoverEffect ? "hover" : undefined}
      {...props}
    >
      {state === "loading" && (
        <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
          <div className="w-8 h-8 border-2 border-primary rounded-full border-t-transparent animate-spin mb-4" />
          <p className="text-sm">{loadingText || "Loading..."}</p>
        </div>
      )}
      {state === "error" && (
        <div className="flex flex-col items-center justify-center py-8 text-destructive">
          <div className="w-10 h-10 border-2 border-destructive rounded-full mb-4 flex items-center justify-center">
            <i className="fas fa-exclamation-triangle text-destructive-foreground" />
          </div>
          <p className="text-sm">{errorText || "Something went wrong"}</p>
        </div>
      )}
      {state === "success" && (
        <div className="flex flex-col items-center justify-center py-8 text-success-foreground">
          <div className="w-10 h-10 border-2 border-success rounded-full mb-4 flex items-center justify-center bg-success/20">
            <i className="fas fa-check-circle text-success-foreground" />
          </div>
          <p className="text-sm">{successText || "Success!"}</p>
        </div>
      )}
      {state === "empty" && (
        <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
          <div className="w-12 h-12 border-2 border-muted rounded-full mb-4 flex items-center justify-center bg-muted/20">
            <i className="fas fa-inbox text-muted-foreground" />
          </div>
          <p className="text-sm">{emptyText || "No data available"}</p>
        </div>
      )}
      {(state === "default" || state === undefined) && (
        <div className="space-y-4">
          {children}
        </div>
      )}
    </motion.div>
  )
})

EnhancedModernCard.displayName = "EnhancedModernCard"

export { EnhancedModernCard, cardVariants }