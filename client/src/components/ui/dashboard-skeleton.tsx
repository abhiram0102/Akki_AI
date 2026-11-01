import * as React from "react";
import { motion } from "framer-motion";
import { motionPresets } from "@/motion";

export const DashboardSkeleton = () => {
  return (
    <motion.div
      initial="initial"
      animate="animate"
      variants={motionPresets.fadeInUp}
      className="space-y-6 px-4"
    >
      <h2 className="text-2xl font-mono font-bold text-white mb-4">
        Dashboard Overview
      </h2>

      <motion.div
        variants={motionPresets.staggerContainer}
        initial="initial"
        animate="animate"
        className="relative space-y-6 px-4 grid gap-4 md:grid-cols-2 lg:grid-cols-4"
      >
        {[1, 2, 3, 4].map((_, index) => (
          <motion.div
            key={index}
            initial="initial"
            animate="animate"
            className="bg-cyan-400/5 border-cyan-400/10 rounded-xl p-4 flex flex-col items-start animate-pulse"
          >
            <div className="flex items-center mb-2 w-full">
              <div className="h-8 w-16 bg-cyan-400/20 rounded-lg animate-pulse" />
              <div className="ml-3 space-y-1">
                <h3 className="h-4 w-24 bg-cyan-400/20 rounded-lg animate-pulse" />
                <p className="h-2 w-16 bg-cyan-400/20 rounded-lg animate-pulse" />
              </div>
            </div>
            <div className="mt-2">
              <div className="h-8 w-20 bg-cyan-400/20 rounded-lg animate-pulse" />
            </div>
          </motion.div>
        ))}
      </motion.div>
    </motion.div>
  );
};