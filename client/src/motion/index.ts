// Motion configuration and presets for the application

import type { Variant } from "framer-motion";
import {
  fadeIn,
  fadeInUp,
  fadeInDown,
  fadeInLeft,
  fadeInRight,
  scaleIn,
  staggerContainer,
  hoverScale,
  pressFeedback,
  pulse,
  float,
  pageTransition,
  routeVariants
} from "./variants";

// Motion presets that can be used throughout the app
export const motionPresets = {
  // Fade animations
  fadeIn,
  fadeInUp,
  fadeInDown,
  fadeInLeft,
  fadeInRight,

  // Scale animations
  scaleIn,

  // Feedback animations
  hoverScale,
  pressFeedback,
  pulse,
  float,

  // Container animations
  staggerContainer,

  // Page/route transitions
  pageTransition,
  routeVariants
};

// Helper function to apply motion variants to elements
export const motionVariants = {
  // For lists and grids
  listItem: (index: number) => ({
    hidden: { opacity: 0, y: 20 },
    animate: {
      opacity: 1,
      y: 0,
      transition: {
        delay: 0.05 * index,
        duration: 0.3
      }
    }
  }),

  // For cards and panels
  card: {
    hidden: { opacity: 0, scale: 0.95 },
    animate: { opacity: 1, scale: 1, transition: { duration: 0.3 } },
    exit: { opacity: 0, scale: 0.9, transition: { duration: 0.2 } }
  },

  // For modals and overlays
  modal: {
    hidden: { opacity: 0, scale: 0.9 },
    animate: { opacity: 1, scale: 1, transition: { duration: 0.3 } },
    exit: { opacity: 0, scale: 0.9, transition: { duration: 0.2 } }
  },

  // For tooltips and popovers
  tooltip: {
    hidden: { opacity: 0, y: -10 },
    animate: { opacity: 1, y: 0, transition: { duration: 0.2 } },
    exit: { opacity: 0, y: -10, transition: { duration: 0.2 } }
  }
};

// Global motion configuration
export const motionConfig = {
  // Default transition settings
  defaultTransition: {
    type: "spring",
    stiffness: 260,
    damping: 20
  },

  // Quick transitions for interactive elements
  quickTransition: {
    duration: 0.15,
    ease: "easeInOut"
  },

  // Smooth transitions for layout changes
  layoutTransition: {
    type: "spring",
    stiffness: 500,
    damping: 20
  },

  // Page transition settings
  pageTransition: {
    duration: 0.4,
    ease: "easeInOut"
  }
};

// Custom hook for using motion variants
export const useMotionVariant = (variantName: keyof typeof motionVariants, index?: number) => {
  if (index !== undefined && typeof motionVariants[variantName] === "function") {
    // @ts-ignore
    return motionVariants[variantName](index);
  }
  return motionVariants[variantName];
};

export default {
  presets: motionPresets,
  variants: motionVariants,
  config: motionConfig,
  useMotionVariant
};