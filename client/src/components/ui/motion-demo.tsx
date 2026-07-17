import * as React from "react";
import { motion } from "framer-motion";
import { motionPresets, motionVariants } from "@/motion";

export const MotionDemo = () => {
  return (
    <div className="space-y-6">
      {/* Fade in animation */}
      <motion.div
        variants={motionPresets.fadeIn}
        initial="initial"
        animate="animate"
        className="p-4 bg-cyber-blue/10 rounded-lg border border-cyber-blue/20"
      >
        <h3 className="text-cyber-blue font-mono">Fade In Demo</h3>
        <p className="text-gray-300">This element fades in when mounted</p>
      </motion.div>

      {/* Staggered list */}
      <motion.div
        variants={motionPresets.staggerContainer}
        initial="initial"
        animate="animate"
        className="space-y-3"
      >
        {[1, 2, 3, 4].map((item) => (
          <motion.div
            key={item}
            variants={{
              initial: { opacity: 0, x: -20 },
              animate: { opacity: 1, x: 0 }
            }}
            initial="initial"
            animate="animate"
            className="p-3 bg-cyber-green/10 rounded-lg border border-cyber-green/20"
          >
            Item {item}
          </motion.div>
        ))}
      </motion.div>

      {/* Hover scale button */}
      <motion.button
        whileHover={motionPresets.hoverScale.whileHover}
        whileTap={motionPresets.pressFeedback.whileTap}
        className="px-6 py-2 bg-gradient-to-r from-cyan-500 to-green-500 text-black font-mono rounded-lg hover:shadow-lg transition-all"
      >
        Hover & Press Me
      </motion.button>

      {/* Pulse animation */}
      <motion.div
        variants={motionPresets.pulse}
        initial="initial"
        animate="animate"
        className="w-16 h-16 bg-cyber-purple/20 rounded-full flex items-center justify-center border border-cyber-purple/30"
      >
        <i className="fas fa-sync text-cyber-pulse animate-spin" />
      </motion.div>

      {/* Float animation */}
      <motion.div
        variants={motionPresets.float}
        initial="initial"
        animate="animate"
        className="w-16 h-16 bg-cyber-amber/20 rounded-full flex items-center justify-center border border-cyber-amber/30"
      >
        <i className="fas fa-cloud text-cyber-amber" />
      </motion.div>
    </div>
  );
};