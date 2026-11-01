import * as React from "react"
import { motion, type Variants, type HTMLMotionProps } from "framer-motion"

import { cn } from "@/lib/utils"

const cardAnimations: Variants = {
  initial: {
    scale: 1,
    opacity: 1,
    filter: "brightness(1)",
  },
  hover: {
    scale: 1.02,
    opacity: 1,
    filter: "brightness(1.05)",
    transition: {
      type: "spring",
      stiffness: 300,
      damping: 20,
    },
  },
}

export interface ModernCardProps
  extends Omit<HTMLMotionProps<"div">, 'variants'> {
  className?: string
  hoverEffect?: boolean
  children: React.ReactNode
}

const ModernCard = React.forwardRef<
  HTMLDivElement,
  ModernCardProps
>(({ className, hoverEffect = true, children, ...props }, ref) => {
  return (
    <motion.div
      ref={ref}
      className={cn(
        "rounded-xl border bg-card text-card-foreground shadow transition-all",
        className
      )}
      variants={cardAnimations}
      whileTap={{ scale: 0.98 }}
      whileHover={hoverEffect ? "hover" : undefined}
      {...props}
    >
      {children}
    </motion.div>
  )
})

ModernCard.displayName = "ModernCard"

// Re-export the original card components for backward compatibility
export { ModernCard }