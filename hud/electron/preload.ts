import { contextBridge, ipcRenderer } from "electron";

const electronBridge = {
  setIgnoreMouseEvents: (ignore: boolean, options?: { forward: boolean }) => {
    ipcRenderer.send("set-ignore-mouse-events", ignore, options);
  },
  setContentProtection: (enable: boolean) => {
    ipcRenderer.send("set-content-protection", enable);
  },
  onPttTriggered: (callback: () => void) => {
    const handler = () => callback();
    ipcRenderer.on("ptt-triggered", handler);
    return () => {
      ipcRenderer.removeListener("ptt-triggered", handler);
    };
  },
  onToggleLayoutMode: (callback: () => void) => {
    const handler = () => callback();
    ipcRenderer.on("toggle-layout-mode", handler);
    return () => {
      ipcRenderer.removeListener("toggle-layout-mode", handler);
    };
  },
  onSetLayoutMode: (callback: (mode: any) => void) => {
    const handler = (_event: any, mode: any) => callback(mode);
    ipcRenderer.on("set-layout-mode", handler);
    return () => {
      ipcRenderer.removeListener("set-layout-mode", handler);
    };
  },
};

// Expose both alfredElectron and electronAPI for seamless compatibility
contextBridge.exposeInMainWorld("alfredElectron", electronBridge);
contextBridge.exposeInMainWorld("electronAPI", electronBridge);
