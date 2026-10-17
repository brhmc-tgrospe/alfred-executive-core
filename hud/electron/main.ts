import { app, BrowserWindow, ipcMain, globalShortcut, screen, Tray, Menu, nativeImage } from "electron";
import * as path from "path";
import * as fs from "fs";

let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;

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

  // Stealth Screen Inspection: Prevent HUD window from being captured by mss/screen recording
  mainWindow.setContentProtection(true);

  // Assert click-through when page finishes loading
  mainWindow.webContents.on("did-finish-load", () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.setIgnoreMouseEvents(true, { forward: true });
    }
  });

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

function createTray() {
  if (tray) return;

  // Resolve tray icon (favor generated 32x32 PNG, fallback to SVG)
  const pngPath = path.join(__dirname, "../public/tray-icon.png");
  const svgPath = path.join(__dirname, "../public/favicon.svg");
  const iconPath = fs.existsSync(pngPath) ? pngPath : svgPath;

  const trayIcon = nativeImage.createFromPath(iconPath);
  tray = new Tray(trayIcon);
  tray.setToolTip("A.L.F.R.E.D. Executive Core");

  const contextMenu = Menu.buildFromTemplate([
    {
      label: "Show / Hide HUD",
      click: () => {
        if (mainWindow && !mainWindow.isDestroyed()) {
          if (mainWindow.isVisible()) {
            mainWindow.hide();
          } else {
            mainWindow.show();
          }
        }
      },
    },
    { type: "separator" },
    {
      label: "Cycle Layout Mode (Ctrl+Shift+A)",
      click: () => {
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.webContents.send("toggle-layout-mode");
        }
      },
    },
    {
      label: "Mode: Cinema (Centered)",
      click: () => {
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.webContents.send("set-layout-mode", "cinema");
        }
      },
    },
    {
      label: "Mode: Docked (Corner)",
      click: () => {
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.webContents.send("set-layout-mode", "docked");
        }
      },
    },
    {
      label: "Mode: Orb-Only (Hide Panels)",
      click: () => {
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.webContents.send("set-layout-mode", "orb_only");
        }
      },
    },
    {
      label: "Force Click-Through (Ctrl+Shift+X)",
      click: () => {
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.setIgnoreMouseEvents(true, { forward: true });
          mainWindow.webContents.send("force-click-through");
        }
      },
    },
    { type: "separator" },
    {
      label: "Mute / Unmute Mic (Ctrl+Space)",
      click: () => {
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.webContents.send("ptt-triggered");
        }
      },
    },
    { type: "separator" },
    {
      label: "Shutdown A.L.F.R.E.D.",
      click: () => {
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(contextMenu);

  tray.on("click", () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      if (mainWindow.isVisible()) {
        mainWindow.hide();
      } else {
        mainWindow.show();
      }
    }
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

// IPC Handler to force desktop click-through
ipcMain.on("force-click-through", () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.setIgnoreMouseEvents(true, { forward: true });
  }
});

// IPC Handler for Stealth Capture (Content Protection)
ipcMain.on("set-content-protection", (_event, enable: boolean) => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.setContentProtection(enable);
  }
});

// IPC Handler for graceful Executive shutdown
ipcMain.on("shutdown-app", () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.close();
  }
  app.quit();
});

app.whenReady().then(() => {
  createWindow();
  createTray();

  // Register Global Push-to-Talk Shortcut (Ctrl+Space on Windows/Linux, Cmd+Space on macOS)
  globalShortcut.register("CommandOrControl+Space", () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("ptt-triggered");
    }
  });

  // Register Global Layout Mode Shortcut (Ctrl+Shift+A on Windows/Linux, Cmd+Shift+A on macOS)
  globalShortcut.register("CommandOrControl+Shift+A", () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("toggle-layout-mode");
    }
  });

  // Register Panic Force Click-Through Shortcut (Ctrl+Shift+X on Windows/Linux, Cmd+Shift+X on macOS)
  globalShortcut.register("CommandOrControl+Shift+X", () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.setIgnoreMouseEvents(true, { forward: true });
      mainWindow.webContents.send("force-click-through");
    }
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
  if (tray) {
    tray.destroy();
    tray = null;
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
