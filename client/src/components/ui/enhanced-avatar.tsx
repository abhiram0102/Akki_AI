"use client"

import * as React from "react"
import * as AvatarPrimitive from "@radix-ui/react-avatar"
import { motion, type Variants, type HTMLMotionProps } from "framer-motion"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const avatarVariants = cva(
  "relative flex shrink-0 overflow-hidden",
  {
    variants: {
      variant: {
        default: "",
        glass: "bg-background/70 backdrop-blur-lg border border-background/30",
        "glass-dark": "bg-background/30 backdrop-blur-lg border border-background/40",
        "neon-glass": "bg-background/60 backdrop-blur-lg border border-background/20 shadow-[0_0_10px_rgba(0,0,0,0.30)]",
        outline: "border border-input",
        subtle: "bg-background/50 border-transparent",
        elevated: "shadow-lg",
        floating: "shadow-xl",
      },
      size: {
        xs: "h-6 w-6",
        sm: "h-8 w-8",
        default: "h-10 w-10",
        lg: "h-12 w-12",
        xl: "h-14 w-14",
        "2xl": "h-16 w-16",
        "3xl": "h-20 w-20",
      },
      shape: {
        round: "rounded-full",
        square: "rounded",
      },
      state: {
        default: "",
        loading: "opacity-75",
        error: "border-destructive/50 bg-destructive/5",
        success: "border-success/50 bg-success/5",
        offline: "opacity-50",
        online: "border-success/50 bg-success/5",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
      shape: "round",
      state: "default",
    },
  }
)

const avatarAnimations: Variants = {
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
  online: {
    scale: [1, 1.1, 1],
    transition: {
      type: "spring",
      stiffness: 300,
      damping: 20,
      repeat: 2,
    },
  },
}

interface EnhancedAvatarProps
  extends Omit<HTMLMotionProps<"span">, 'variants'> {
  className?: string
  variant?: "default" | "glass" | "glass-dark" | "neon-glass" | "outline" | "subtle" | "elevated" | "floating"
  size?: "xs" | "sm" | "default" | "lg" | "xl" | "2xl" | "3xl"
  shape?: "round" | "square"
  state?: "default" | "loading" | "error" | "success" | "offline" | "online"
  hoverEffect?: boolean
  online?: boolean
}

const EnhancedAvatar = React.forwardRef<
  React.ElementRef<typeof AvatarPrimitive.Root>,
  EnhancedAvatarProps
>(({ className, variant = "default", size = "default", shape = "round", state = "default", hoverEffect = true, online = false, ...props }, ref) => {
  const baseClasses = cn(
    avatarVariants({ variant, size, shape, state, className })
  )

  // Add online indicator class if needed
  const finalClasses = online ? cn(baseClasses, "border-success/[0.5] bg-success/[0.5]") : baseClasses

  return (
    <motion.span
      ref={ref}
      className={finalClasses}
      variants={avatarAnimations}
      initial="initial"
      animate="animate"
      whileTap="press"
      whileHover={hoverEffect ? "hover" : undefined}
      {...props}
    />
  )
})
EnhancedAvatar.displayName = AvatarPrimitive.Root.displayName

const EnhancedAvatarImage = React.forwardRef<
  React.ElementRef<typeof AvatarPrimitive.Image>,
  React.ComponentPropsWithoutRef<typeof AvatarPrimitive.Image>
>(({ className, ...props }, ref) => (
  <AvatarPrimitive.Image
    ref={ref}
    className={cn("aspect-square h-full w-full", className)}
    {...props}
  />
))
EnhancedAvatarImage.displayName = AvatarPrimitive.Image.displayName

const EnhancedAvatarFallback = React.forwardRef<
  React.ElementRef<typeof AvatarPrimitive.Fallback>,
  React.ComponentPropsWithoutRef<typeof AvatarPrimitive.Fallback>
>(({ className, ...props }, ref) => (
  <AvatarPrimitive.Fallback
    ref={ref}
    className={cn(
      "flex h-full w-full items-center justify-center rounded-full bg-muted",
      className
    )}
    {...props}
  />
))
EnhancedAvatarFallback.displayName = AvatarPrimitive.Fallback.displayName

export { EnhancedAvatar, EnhancedAvatarImage, EnhancedAvatarFallback, avatarVariants }