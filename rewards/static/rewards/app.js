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

const connectionSequence = document.querySelector("[data-connection-sequence]");
if (connectionSequence) {
  const variant = connectionSequence.dataset.variant || "welcome";
  const key = `family-circle-connected-${variant}`;
  let alreadyShown = false;
  try {
    alreadyShown = window.sessionStorage.getItem(key) === "yes";
    window.sessionStorage.setItem(key, "yes");
  } catch (error) {
    // Launch animation still works when storage is blocked.
  }
  if (alreadyShown) {
    connectionSequence.remove();
  } else {
    document.body.classList.add("connecting");
    window.setTimeout(() => {
      connectionSequence.classList.add("connected");
      document.body.classList.remove("connecting");
      window.setTimeout(() => connectionSequence.remove(), 450);
    }, variant === "child" ? 1550 : 1250);
  }
}

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

const paymentSuccess = document.querySelector(".toast.payment-success");
if (paymentSuccess) {
  const paymentOverlay = document.createElement("section");
  const spent = paymentSuccess.classList.contains("spent");
  paymentOverlay.className = "payment-confirmation";
  paymentOverlay.setAttribute("role", "status");
  paymentOverlay.innerHTML = `
    <div class="payment-check"><span></span></div>
    <p>${spent ? "Spend requested" : "Sent successfully"}</p>
    <strong>${paymentSuccess.textContent}</strong>
    <small>${spent ? "Reserved until Dad verifies the purchase" : "Your family payment is complete"}</small>
  `;
  paymentSuccess.remove();
  document.body.appendChild(paymentOverlay);
  window.setTimeout(() => paymentOverlay.classList.add("fade-out"), 2100);
  window.setTimeout(() => paymentOverlay.remove(), 2500);
} else if (document.querySelector(".toast.success")) {
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
      countdown.textContent = countdown.dataset.expiredMessage || "Time is up for today's credit";
      countdown.classList.add("expired");
      if (countdown.dataset.disableQuestButtons === "true") {
        const board = countdown.closest(".bonus-quest-board");
        if (board) {
          board.querySelectorAll(".quest-button").forEach((button) => {
            button.disabled = true;
            button.textContent = "Expired";
          });
        }
      }
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

document.querySelectorAll("[data-grounding-deadline]").forEach((countdown) => {
  const deadline = new Date(countdown.dataset.groundingDeadline).getTime();
  function updateGroundingCountdown() {
    const remaining = deadline - Date.now();
    if (remaining <= 0) {
      countdown.textContent = "Releasing Grounded Mode...";
      if (!countdown.dataset.releaseRequested) {
        countdown.dataset.releaseRequested = "true";
        window.setTimeout(() => window.location.reload(), 500);
      }
      return;
    }
    const minutes = Math.ceil(remaining / 60000);
    const days = Math.floor(minutes / (24 * 60));
    const hours = Math.floor((minutes % (24 * 60)) / 60);
    const rest = minutes % 60;
    countdown.textContent = days ? `${days}d ${hours}h ${rest}m` : `${hours}h ${rest}m`;
  }
  updateGroundingCountdown();
  window.setInterval(updateGroundingCountdown, 60000);
});

document.querySelectorAll("[data-open-review]").forEach((button) => {
  button.addEventListener("click", () => {
    const dialog = document.getElementById(button.dataset.openReview);
    if (dialog) dialog.showModal();
  });
});

document.querySelectorAll("[data-open-dialog]").forEach((button) => {
  button.addEventListener("click", () => {
    const dialog = document.getElementById(button.dataset.openDialog);
    if (dialog) dialog.showModal();
  });
});

const guardianGrid = document.querySelector(".guardian .grid");
if (guardianGrid) {
  const modules = Array.from(guardianGrid.querySelectorAll("[data-dashboard-module]"));
  if (modules.length) {
    const launcher = document.createElement("article");
    launcher.className = "card module-launcher";
    launcher.innerHTML = '<div class="card-head"><h2>Dashboard Modules</h2><span class="badge">Open a view</span></div><div class="module-grid"></div>';
    const buttonGrid = launcher.querySelector(".module-grid");
    modules.forEach((module, index) => {
      const title = module.dataset.dashboardModule;
      const id = `dashboard-module-${index}`;
      const dialog = document.createElement("dialog");
      dialog.className = "review-dialog feature-dialog guardian-feature-dialog";
      dialog.id = id;
      dialog.innerHTML = '<form method="dialog" class="dialog-close"><button aria-label="Close">&times;</button></form>';
      module.before(dialog);
      dialog.appendChild(module);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "module-tile";
      button.textContent = title;
      button.addEventListener("click", () => dialog.showModal());
      buttonGrid.appendChild(button);
    });
    guardianGrid.prepend(launcher);
  }
}

document.querySelectorAll("[data-auto-open-dialog]").forEach((dialog) => {
  if (dialog.showModal) dialog.showModal();
});

document.querySelectorAll("[data-confirm-deduction]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm("Remove these tokens for the recorded behavior reason?")) event.preventDefault();
  });
});

document.querySelectorAll("[data-money-pad]").forEach((pad) => {
  const field = pad.querySelector("[data-money-input]");
  const display = pad.querySelector("[data-money-display]");
  let typedAmount = "";

  function updateAmount() {
    const amount = Number.parseFloat(typedAmount || "0");
    field.value = amount.toFixed(2);
    display.textContent = typedAmount || "0";
  }

  pad.querySelectorAll("[data-money-key]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.moneyKey;
      if (key === "." && typedAmount.includes(".")) return;
      if (key === "." && typedAmount === "") typedAmount = "0";
      const decimalPlaces = typedAmount.includes(".") ? typedAmount.split(".")[1].length : 0;
      if (key !== "." && decimalPlaces >= 2) return;
      if (key !== "." && !typedAmount.includes(".") && typedAmount === "0") typedAmount = "";
      typedAmount += key;
      updateAmount();
    });
  });

  const deleteButton = pad.querySelector("[data-money-delete]");
  if (deleteButton) {
    deleteButton.addEventListener("click", () => {
      typedAmount = typedAmount.slice(0, -1);
      updateAmount();
    });
  }

  pad.addEventListener("submit", (event) => {
    if (Number.parseFloat(field.value) <= 0) {
      event.preventDefault();
      toast("Enter an amount first.");
    }
  });

  updateAmount();
});
