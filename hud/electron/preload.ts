import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("electronAPI", {
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
});
