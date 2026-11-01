import { useState } from "react";
import { motion, AnimatePresence, type HTMLMotionProps } from "framer-motion";

// Omit motion's own onAnimationStart/onDrag* to avoid conflict with HTMLButtonElement
type MotionButtonProps = Omit<
  HTMLMotionProps<"button">,
  "variant" | "size" | "style"
>;

export interface CyberButtonProps extends MotionButtonProps {
  variant?: "primary" | "danger" | "ghost" | "amber";
  isLoading?: boolean;
  icon?: string;
  fullWidth?: boolean;
  size?: "sm" | "md" | "lg";
  style?: React.CSSProperties;
}

const COLORS = {
  primary: { base: "rgba(0,216,255,",  hex: "#00d8ff" },
  danger:  { base: "rgba(255,56,104,", hex: "#ff3868" },
  amber:   { base: "rgba(255,183,0,",  hex: "#ffb700" },
  ghost:   { base: "rgba(255,255,255,",hex: "rgba(255,255,255,0.65)" },
};

const SIZES = {
  sm: { padding: "6px 14px",  fontSize: 11, iconSize: 10 },
  md: { padding: "10px 20px", fontSize: 13, iconSize: 12 },
  lg: { padding: "13px 28px", fontSize: 14, iconSize: 13 },
};

export function CyberButton({
  variant = "primary",
  isLoading = false,
  icon,
  fullWidth = false,
  size = "md",
  children,
  disabled,
  style: externalStyle,
  onClick,
  ...props
}: CyberButtonProps) {
  const [hovered, setHovered] = useState(false);
  const c = COLORS[variant];
  const s = SIZES[size];
  const isDisabled = disabled || isLoading;

  const baseStyle: React.CSSProperties = {
    position: "relative",
    overflow: "hidden",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    width: fullWidth ? "100%" : undefined,
    padding: s.padding,
    borderRadius: 10,
    border: `1px solid ${
      variant === "ghost"
        ? hovered ? "rgba(255,255,255,0.18)" : "rgba(255,255,255,0.07)"
        : hovered ? `${c.base}0.65)` : `${c.base}0.28)`
    }`,
    background:
      variant === "ghost"
        ? hovered ? "rgba(255,255,255,0.05)" : "transparent"
        : hovered ? `${c.base}0.13)` : `${c.base}0.06)`,
    color:
      variant === "ghost"
        ? hovered ? "#fff" : "rgba(255,255,255,0.45)"
        : c.hex,
    fontFamily: "monospace",
    fontWeight: 700,
    fontSize: s.fontSize,
    letterSpacing: "0.06em",
    cursor: isDisabled ? "not-allowed" : "pointer",
    opacity: isDisabled ? 0.5 : 1,
    boxShadow: hovered && !isDisabled ? `0 0 20px ${c.base}0.14)` : "none",
    transition: "background 0.15s, border-color 0.15s, box-shadow 0.15s, color 0.15s",
    userSelect: "none",
    textTransform: "uppercase" as const,
    ...externalStyle,
  };

  return (
    <motion.button
      style={baseStyle}
      onHoverStart={() => !isDisabled && setHovered(true)}
      onHoverEnd={() => setHovered(false)}
      whileTap={isDisabled ? {} : { scale: 0.97 }}
      disabled={isDisabled}
      onClick={onClick}
      {...props}
    >
      <AnimatePresence>
        {hovered && !isDisabled && (
          <motion.span
            key="sweep"
            initial={{ x: "-100%" }}
            animate={{ x: "160%" }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.45, ease: "easeOut" }}
            style={{
              position: "absolute",
              inset: 0,
              background: `linear-gradient(90deg, transparent, ${c.base}0.20), transparent)`,
              pointerEvents: "none",
            }}
          />
        )}
      </AnimatePresence>

      {isLoading ? (
        <>
          <i className="fas fa-circle-notch fa-spin" style={{ fontSize: s.iconSize }} />
          <span>Loading…</span>
        </>
      ) : (
        <>
          {icon && <i className={icon} style={{ fontSize: s.iconSize }} />}
          {children}
        </>
      )}
    </motion.button>
  );
}
