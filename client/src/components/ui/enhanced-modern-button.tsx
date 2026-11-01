import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"
import { motion, type Variants, type HTMLMotionProps } from "framer-motion"

import {cn} from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground shadow hover:bg-primary/90",
        destructive:
          "bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90",
        outline:
          "border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground",
        secondary:
          "bg-secondary text-secondary-foreground shadow-sm hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
        // Glassmorphism variants
        glass: "bg-primary/70 text-primary-foreground backdrop-blur-lg border border-primary/30 hover:bg-primary/80",
        "glass-dark": "bg-primary/30 text-primary-foreground backdrop-blur-lg border border-primary/40 hover:bg-primary/40",
        "neon-glass": "bg-primary/60 text-primary-foreground backdrop-blur-lg border border-primary/20 shadow-[0_0_15px_rgba(0,191,255,0.50)] hover:bg-primary/70",
        "neon-outline": "border border-primary/20 bg-transparent text-primary-foreground shadow-[0_0_10px_rgba(0,191,255,0.30)] hover:bg-primary/10 hover:text-primary-foreground",
        subtle: "bg-muted/50 text-muted-foreground hover:bg-muted/60",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-10 rounded-md px-8",
        icon: "h-9 w-9",
        xs: "h-7 rounded px-2 text-xs",
        xl: "h-11 rounded-md px-8 py-3 text-lg",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

const buttonAnimations: Variants = {
  initial: {
    scale: 0.95,
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
    opacity: 1,
    transition: {
      type: "spring",
      stiffness: 300,
      damping: 20,
    },
  },
  press: {
    scale: 0.95,
    opacity: 1,
    transition: {
      type: "spring",
      stiffness: 500,
      damping: 20,
    },
  },
  exit: {
    scale: 0.9,
    opacity: 0,
    transition: {
      type: "spring",
      stiffness: 300,
      damping: 20,
    },
  },
}

export interface EnhancedModernButtonProps
  extends Omit<HTMLMotionProps<"button">, 'variants' | keyof VariantProps<typeof buttonVariants>>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
  variant?: "default" | "destructive" | "outline" | "secondary" | "ghost" | "link" | "glass" | "glass-dark" | "neon-glass" | "neon-outline" | "subtle"
  size?: "default" | "sm" | "lg" | "icon" | "xs" | "xl"
  isLoading?: boolean
  loadingText?: string
  loadingPosition?: "left" | "right" | "only"
}

const EnhancedModernButton = React.forwardRef<
  HTMLButtonElement,
  EnhancedModernButtonProps
>(({ className, variant, size, asChild = false, isLoading = false, loadingText = "Loading...", loadingPosition = "left", children, ...props }, ref) => {
  const Comp = asChild ? Slot : "button"

  return (
    <motion.button
      className={cn(buttonVariants({ variant, size, className }))}
      ref={ref}
      variants={buttonAnimations}
      initial="initial"
      animate="animate"
      whileTap="press"
      whileHover="hover"
      disabled={isLoading}
      {...props}
    >
      {isLoading ? (
        <>
          {loadingPosition !== "right" && loadingPosition !== "only" && (
            <>
              <span className="mr-2 h-4 w-4 animate-spin border-2 border-primary rounded-full border-t-transparent" />
              {loadingText}
            </>
          )}
          {loadingPosition === "only" && (
            <span className="h-4 w-4 animate-spin border-2 border-primary rounded-full border-t-transparent" />
          )}
          {loadingPosition !== "left" && loadingPosition !== "only" && (
            <>
              {loadingText}
              <span className="ml-2 h-4 w-4 animate-spin border-2 border-primary rounded-full border-t-transparent" />
            </>
          )}
        </>
      ) : (
        children
      )}
    </motion.button>
  )
})

EnhancedModernButton.displayName = "EnhancedModernButton"

export { EnhancedModernButton, buttonVariants }