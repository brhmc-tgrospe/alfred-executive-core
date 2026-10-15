import { useState, useEffect, useRef } from "react";

/**
 * Custom React hook tracking real-time rendering frames per second (FPS)
 * using requestAnimationFrame with 1.0s window averaging.
 */
export function useFps(): number {
  const [fps, setFps] = useState<number>(60);
  const frameCount = useRef<number>(0);
  const lastTime = useRef<number>(performance.now());
  const animId = useRef<number>(0);

  useEffect(() => {
    const loop = (now: number) => {
      frameCount.current++;
      const delta = now - lastTime.current;
      if (delta >= 1000) {
        const calculatedFps = Math.round((frameCount.current * 1000) / delta);
        setFps(calculatedFps);
        frameCount.current = 0;
        lastTime.current = now;
      }
      animId.current = requestAnimationFrame(loop);
    };

    animId.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(animId.current);
  }, []);

  return fps;
}
