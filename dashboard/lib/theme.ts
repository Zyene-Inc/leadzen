export type Theme = "light" | "dark";
export const themeStorageKey = "leadzen.theme";
const themeChanged = "leadzen:theme-change";

// Runs in the document head before paint. Only a validated preference is applied.
export const themeBootstrap = `(function(){try{var t=localStorage.getItem("${themeStorageKey}");document.documentElement.dataset.theme=t==="dark"?"dark":"light"}catch(e){}})()`;

export function getTheme(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

export function getServerTheme(): Theme {
  return "light";
}

export function setTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  try {
    window.localStorage.setItem(themeStorageKey, theme);
  } catch {
    // The control still works for this session when browser storage is blocked.
  }
  window.dispatchEvent(new Event(themeChanged));
}

export function subscribeToTheme(notify: () => void) {
  function onStorage(event: StorageEvent) {
    if (event.key !== themeStorageKey && event.key !== null) return;
    if (event.storageArea) {
      try {
        if (event.storageArea !== window.localStorage) return;
      } catch {
        return;
      }
    }
    document.documentElement.dataset.theme = event.newValue === "dark" ? "dark" : "light";
    notify();
  }
  window.addEventListener(themeChanged, notify);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(themeChanged, notify);
    window.removeEventListener("storage", onStorage);
  };
}
