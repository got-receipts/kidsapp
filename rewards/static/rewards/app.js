if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js"));
}

window.setTimeout(() => {
  document.querySelectorAll(".toast").forEach((toast) => toast.remove());
}, 4500);
