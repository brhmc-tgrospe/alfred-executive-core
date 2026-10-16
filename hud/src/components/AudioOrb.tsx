import { useEffect, useRef } from "react";
import * as THREE from "three";
import type { AlfredStatus } from "../types";

interface AudioOrbProps {
  rmsVolume: number;
  status: AlfredStatus;
  size?: number;
}

const STATUS_COLORS: Record<AlfredStatus, number> = {
  idle: 0x06b6d4, // Ice Cyan (#06b6d4)
  listening: 0x06b6d4, // Ice Cyan
  thinking: 0xf59e0b, // Executive Gold (#f59e0b)
  speaking: 0x10b981, // Emerald (#10b981)
};

export function AudioOrb({ rmsVolume, status, size = 280 }: AudioOrbProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const sizeRef = useRef<number>(size);

  // Mutable refs to prevent React state re-renders at 60 FPS
  const rmsRef = useRef<number>(rmsVolume);
  const statusRef = useRef<AlfredStatus>(status);

  // Keep refs up-to-date with incoming props
  useEffect(() => {
    rmsRef.current = rmsVolume;
  }, [rmsVolume]);

  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  // Decoupled dynamic resizing without scene recreation
  useEffect(() => {
    sizeRef.current = size;
    if (rendererRef.current && cameraRef.current) {
      rendererRef.current.setSize(size, size);
      cameraRef.current.aspect = 1;
      cameraRef.current.updateProjectionMatrix();
    }
  }, [size]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // 1. Scene, Camera, Renderer Setup
    const width = sizeRef.current;
    const height = sizeRef.current;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
    camera.position.z = 4.2;
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    rendererRef.current = renderer;
    container.appendChild(renderer.domElement);

    // 2. Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.8);
    scene.add(ambientLight);

    const pointLight = new THREE.PointLight(STATUS_COLORS[statusRef.current], 3.0, 10);
    pointLight.position.set(0, 0, 0);
    scene.add(pointLight);

    // 3. Gyroscope Nested Rings (Torus)
    const initialColor = new THREE.Color(STATUS_COLORS[statusRef.current]);

    // Outer Ring
    const outerRingGeo = new THREE.TorusGeometry(1.4, 0.022, 16, 120);
    const outerRingMat = new THREE.MeshStandardMaterial({
      color: initialColor.clone(),
      roughness: 0.2,
      metalness: 0.9,
      emissive: initialColor.clone(),
      emissiveIntensity: 0.35,
    });
    const outerRing = new THREE.Mesh(outerRingGeo, outerRingMat);
    scene.add(outerRing);

    // Middle Ring
    const midRingGeo = new THREE.TorusGeometry(1.12, 0.02, 16, 100);
    const midRingMat = new THREE.MeshStandardMaterial({
      color: initialColor.clone(),
      roughness: 0.2,
      metalness: 0.85,
      emissive: initialColor.clone(),
      emissiveIntensity: 0.4,
    });
    const midRing = new THREE.Mesh(midRingGeo, midRingMat);
    scene.add(midRing);

    // Inner Ring
    const innerRingGeo = new THREE.TorusGeometry(0.85, 0.018, 16, 80);
    const innerRingMat = new THREE.MeshStandardMaterial({
      color: initialColor.clone(),
      roughness: 0.15,
      metalness: 0.8,
      emissive: initialColor.clone(),
      emissiveIntensity: 0.45,
    });
    const innerRing = new THREE.Mesh(innerRingGeo, innerRingMat);
    scene.add(innerRing);

    // 4. Central Glowing Icosahedron Core
    const coreGeo = new THREE.IcosahedronGeometry(0.46, 2);
    const coreMat = new THREE.MeshStandardMaterial({
      color: initialColor.clone(),
      wireframe: true,
      roughness: 0.1,
      metalness: 0.95,
      emissive: initialColor.clone(),
      emissiveIntensity: 0.6,
    });
    const core = new THREE.Mesh(coreGeo, coreMat);
    scene.add(core);

    // Inner Solid Glow Sphere
    const innerGlowGeo = new THREE.SphereGeometry(0.24, 24, 24);
    const innerGlowMat = new THREE.MeshBasicMaterial({
      color: initialColor.clone(),
      transparent: true,
      opacity: 0.75,
    });
    const innerGlow = new THREE.Mesh(innerGlowGeo, innerGlowMat);
    scene.add(innerGlow);

    // Particles Cloud Orbit
    const particleCount = 100;
    const particleGeo = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    for (let i = 0; i < particleCount; i++) {
      const radius = 1.6 + Math.random() * 0.4;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
      positions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
      positions[i * 3 + 2] = radius * Math.cos(phi);
    }
    particleGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const particleMat = new THREE.PointsMaterial({
      color: initialColor.clone(),
      size: 0.035,
      transparent: true,
      opacity: 0.6,
    });
    const particles = new THREE.Points(particleGeo, particleMat);
    scene.add(particles);

    // 5. 60 FPS Animation Loop
    let animId: number;
    let smoothRms = 0;
    const targetColor = new THREE.Color(STATUS_COLORS[statusRef.current]);

    const animate = () => {
      animId = requestAnimationFrame(animate);

      // Smooth RMS Dampening
      const currentRms = Math.min(Math.max(rmsRef.current || 0, 0), 1.0);
      smoothRms += (currentRms - smoothRms) * 0.18;

      // Update Target Color based on status
      const currentStatus = statusRef.current;
      const hexColor = STATUS_COLORS[currentStatus] || STATUS_COLORS.idle;
      targetColor.setHex(hexColor);

      // Lerp Material Colors
      const lerpFactor = 0.08;
      outerRingMat.color.lerp(targetColor, lerpFactor);
      outerRingMat.emissive.lerp(targetColor, lerpFactor);
      midRingMat.color.lerp(targetColor, lerpFactor);
      midRingMat.emissive.lerp(targetColor, lerpFactor);
      innerRingMat.color.lerp(targetColor, lerpFactor);
      innerRingMat.emissive.lerp(targetColor, lerpFactor);
      coreMat.color.lerp(targetColor, lerpFactor);
      coreMat.emissive.lerp(targetColor, lerpFactor);
      innerGlowMat.color.lerp(targetColor, lerpFactor);
      particleMat.color.lerp(targetColor, lerpFactor);
      pointLight.color.lerp(targetColor, lerpFactor);

      // Dynamic Speed modulated by RMS and Status
      const speedMultiplier = currentStatus === "speaking" ? 1.6 : currentStatus === "thinking" ? 1.2 : 1.0;
      const audioPulse = 1.0 + smoothRms * 1.5;

      // Gimbal Ring 3-Axis Rotations
      outerRing.rotation.x += 0.007 * speedMultiplier;
      outerRing.rotation.y += 0.011 * speedMultiplier;

      midRing.rotation.y += 0.013 * speedMultiplier;
      midRing.rotation.z += 0.008 * speedMultiplier;

      innerRing.rotation.z += 0.017 * speedMultiplier;
      innerRing.rotation.x += 0.009 * speedMultiplier;

      // Core rotation & scale pulsing
      core.rotation.x -= 0.012 * speedMultiplier;
      core.rotation.y += 0.018 * speedMultiplier;
      core.scale.setScalar(audioPulse);

      innerGlow.scale.setScalar(1.0 + smoothRms * 2.2);

      // Particle subtle drifting rotation
      particles.rotation.y += 0.002 * speedMultiplier;
      particles.rotation.x += 0.001 * speedMultiplier;

      renderer.render(scene, camera);
    };

    animate();

    // 6. Cleanup
    return () => {
      cancelAnimationFrame(animId);
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
      outerRingGeo.dispose();
      outerRingMat.dispose();
      midRingGeo.dispose();
      midRingMat.dispose();
      innerRingGeo.dispose();
      innerRingMat.dispose();
      coreGeo.dispose();
      coreMat.dispose();
      innerGlowGeo.dispose();
      innerGlowMat.dispose();
      particleGeo.dispose();
      particleMat.dispose();
      renderer.dispose();
      rendererRef.current = null;
      cameraRef.current = null;
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className="relative flex items-center justify-center transition-all duration-300 pointer-events-none"
      style={{ width: size, height: size }}
    />
  );
}
