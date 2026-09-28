import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

/**
 * Shared easing for LifeLine: a soft decelerating curve. Motion is deliberately
 * restrained — a healthcare product should feel calm, not animated for its own
 * sake. Every helper collapses to a static render when the user prefers
 * reduced motion.
 */
const EASE: [number, number, number, number] = [0.16, 1, 0.3, 1];

interface RevealProps {
  children: ReactNode;
  /** Seconds to wait before starting — used to stagger a row of items. */
  delay?: number;
  /** Distance in px the element travels up on entry. */
  y?: number;
  className?: string;
}

/** Fades and slides content in once, the first time it scrolls into view. */
export function Reveal({ children, delay = 0, y = 14, className }: RevealProps) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduce ? false : { opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.2 }}
      transition={{ duration: 0.45, delay, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}

/** Fades and slides content in immediately on mount (no scroll dependency). */
export function FadeIn({ children, delay = 0, className }: Omit<RevealProps, "y">) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}

/** A list row that fades up on mount, offset by its position in the list. */
export function StaggerItem({
  children,
  index = 0,
  className,
  step = 0.035,
}: {
  children: ReactNode;
  index?: number;
  className?: string;
  step?: number;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index, 8) * step, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}
