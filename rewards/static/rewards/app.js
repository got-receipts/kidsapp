if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js"));
}

function cookieValue(name) {
  const entry = document.cookie.split("; ").find((part) => part.startsWith(`${name}=`));
  return entry ? decodeURIComponent(entry.split("=")[1]) : "";
}

function toast(message) {
  const holder = document.querySelector(".messages") || document.body.appendChild(Object.assign(document.createElement("div"), { className: "messages" }));
  const notice = document.createElement("div");
  notice.className = "toast";
  notice.textContent = message;
  holder.appendChild(notice);
  window.setTimeout(() => notice.remove(), 4500);
}

function toApplicationKey(value) {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(window.atob(base64), (character) => character.charCodeAt(0));
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try {
    window.localStorage.setItem("family-circle-theme", theme);
  } catch (error) {
    // A restricted browser may block storage; the active theme still applies.
  }
  const themeColor = document.querySelector('meta[name="theme-color"]');
  if (themeColor) themeColor.setAttribute("content", theme === "dark" ? "#091321" : "#14263d");
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.setAttribute("aria-label", theme === "dark" ? "Switch to light theme" : "Switch to dark theme");
  });
}

setTheme(document.documentElement.dataset.theme || "light");
document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
  button.addEventListener("click", () => {
    setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  });
});

const notificationButton = document.querySelector("#enable-notifications");
if (notificationButton) {
  notificationButton.addEventListener("click", async () => {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      toast("Push notifications are not available on this device.");
      return;
    }
    const key = notificationButton.dataset.vapidKey;
    if (!key) {
      toast("Push keys need to be configured before reminders can be enabled.");
      return;
    }
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        toast("Notification permission was not enabled.");
        return;
      }
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: toApplicationKey(key),
      });
      const response = await fetch(notificationButton.dataset.subscribeUrl, {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-CSRFToken": cookieValue("csrftoken")},
        body: JSON.stringify(subscription),
      });
      if (!response.ok) throw new Error("subscription rejected");
      notificationButton.textContent = "Star reminders are on";
      notificationButton.disabled = true;
      toast("You will receive the 7:30 PM good behavior star reminder.");
    } catch (error) {
      toast("Could not enable notifications on this device.");
    }
  });
}

if (document.querySelector(".toast.success")) {
  const celebration = document.createElement("div");
  celebration.className = "celebration";
  celebration.innerHTML = "<span></span><span></span><span></span><span></span><span></span>";
  document.body.appendChild(celebration);
  window.setTimeout(() => celebration.remove(), 1500);
}

window.setTimeout(() => {
  document.querySelectorAll(".toast").forEach((toast) => toast.remove());
}, 4500);

document.querySelectorAll("[data-quest-deadline]").forEach((countdown) => {
  const deadline = new Date(countdown.dataset.questDeadline).getTime();
  function updateCountdown() {
    const remaining = deadline - Date.now();
    if (remaining <= 0) {
      countdown.textContent = "Time is up for today's credit";
      countdown.classList.add("expired");
      return;
    }
    const totalSeconds = Math.floor(remaining / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    countdown.textContent = `${hours}h ${minutes}m ${seconds}s left`;
  }
  updateCountdown();
  window.setInterval(updateCountdown, 1000);
});
