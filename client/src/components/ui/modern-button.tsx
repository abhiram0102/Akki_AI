import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"
import { motion, type Variants, type HTMLMotionProps } from "framer-motion"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow hover:bg-primary/90",
        destructive:
          "bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90",
        outline:
          "border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground",
        secondary:
          "bg-secondary text-secondary-foreground shadow-sm hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-10 rounded-md px-8",
        icon: "h-9 w-9",
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
    scale: 1,
    opacity: 1,
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
}

export interface ModernButtonProps
  extends Omit<HTMLMotionProps<"button">, 'variants' | keyof VariantProps<typeof buttonVariants>>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
  variant?: "default" | "destructive" | "outline" | "secondary" | "ghost" | "link"
  size?: "default" | "sm" | "lg" | "icon"
  isLoading?: boolean
  loadingText?: string
}

const ModernButton = React.forwardRef<
  HTMLButtonElement,
  ModernButtonProps
>(({
  className,
  variant,
  size,
  asChild = false,
  isLoading = false,
  loadingText = "Loading...",
  children,
  ...props
}, ref) => {
  const Comp = asChild ? Slot : "button"

  return (
    <motion.button
      className={cn(buttonVariants({ variant, size, className }))}
      ref={ref}
      variants={buttonAnimations}
      whileTap="press"
      whileHover="hover"
      disabled={isLoading}
      {...props}
    >
      {isLoading ? (
        <>
          <span className="mr-2 h-4 w-4 animate-spin border-2 border-primary rounded-full border-t-transparent" />
          <span>{loadingText}</span>
        </>
      ) : (
        children
      )}
    </motion.button>
  )
})

ModernButton.displayName = "ModernButton"

export { ModernButton, buttonVariants }