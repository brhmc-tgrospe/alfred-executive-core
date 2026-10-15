import { app, BrowserWindow, ipcMain, globalShortcut, screen } from "electron";
import * as path from "path";

let mainWindow: BrowserWindow | null = null;

function createWindow() {
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width, height } = primaryDisplay.workAreaSize;

  mainWindow = new BrowserWindow({
    width,
    height,
    x: 0,
    y: 0,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    hasShadow: false,
    resizable: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // Default to pass-through mouse events so user can interact with their desktop behind the HUD
  mainWindow.setIgnoreMouseEvents(true, { forward: true });

  const devServerUrl = process.env.VITE_DEV_SERVER_URL;
  if (devServerUrl) {
    mainWindow.loadURL(devServerUrl);
  } else {
    mainWindow.loadFile(path.join(__dirname, "../dist/index.html"));
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// IPC Handlers for toggling mouse events when hovering over HUD widgets
ipcMain.on("set-ignore-mouse-events", (_event, ignore: boolean, options?: { forward: boolean }) => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    if (ignore) {
      mainWindow.setIgnoreMouseEvents(true, options ?? { forward: true });
    } else {
      mainWindow.setIgnoreMouseEvents(false);
    }
  }
});

app.whenReady().then(() => {
  createWindow();

  // Register Global Push-to-Talk Shortcut (Ctrl+Space on Windows/Linux, Cmd+Space on macOS)
  const registered = globalShortcut.register("CommandOrControl+Space", () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("ptt-triggered");
    }
  });

  if (!registered) {
    console.warn("Global shortcut registration failed for CommandOrControl+Space");
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
