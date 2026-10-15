import { contextBridge, ipcRenderer } from "electron";

const electronBridge = {
  setIgnoreMouseEvents: (ignore: boolean, options?: { forward: boolean }) => {
    ipcRenderer.send("set-ignore-mouse-events", ignore, options);
  },
  onPttTriggered: (callback: () => void) => {
    const handler = () => callback();
    ipcRenderer.on("ptt-triggered", handler);
    return () => {
      ipcRenderer.removeListener("ptt-triggered", handler);
    };
  },
};

// Expose both alfredElectron and electronAPI for seamless compatibility
contextBridge.exposeInMainWorld("alfredElectron", electronBridge);
contextBridge.exposeInMainWorld("electronAPI", electronBridge);
