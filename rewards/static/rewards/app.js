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
    const liveStatus = connectionSequence.querySelector(".connection-live");
    const statusByVariant = {
      child: ["Gathering today's quests", "Charging your star map", "Adventure board ready"],
      guardian: ["Validating protected access", "Syncing family schedules", "Command center ready"],
      welcome: ["Establishing private connection", "Linking the family network", "Connection ready"],
    };
    const statuses = statusByVariant[variant] || statusByVariant.welcome;
    window.setTimeout(() => { if (liveStatus) liveStatus.textContent = statuses[1]; }, 700);
    window.setTimeout(() => { if (liveStatus) liveStatus.textContent = statuses[2]; }, 1500);
    const duration = variant === "child" ? 2700 : variant === "guardian" ? 2350 : 2200;
    window.setTimeout(() => {
      connectionSequence.classList.add("connected");
      document.body.classList.remove("connecting");
      window.setTimeout(() => connectionSequence.remove(), 600);
    }, duration);
  }
}

const notificationButtons = document.querySelectorAll("[data-enable-notifications]");
notificationButtons.forEach((notificationButton) => {
  notificationButton.addEventListener("click", async () => {
    if (!("Notification" in window) || !("serviceWorker" in navigator) || !("PushManager" in window)) {
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
      notificationButtons.forEach((button) => {
        button.textContent = "Reminders are on";
        button.disabled = true;
      });
      const notificationPrompt = document.querySelector("[data-notification-prompt]");
      if (notificationPrompt && notificationPrompt.open) notificationPrompt.close();
      toast("Star check-ins and schedule planning reminders are enabled.");
    } catch (error) {
      toast("Could not enable notifications on this device.");
    }
  });
});

const notificationPrompt = document.querySelector("[data-notification-prompt]");
if (notificationPrompt && (!("Notification" in window) || Notification.permission === "default")) {
  let alreadyPrompted = false;
  try {
    alreadyPrompted = window.localStorage.getItem("family-circle-notification-prompted") === "yes";
  } catch (error) {
    // The prompt can still appear when storage is restricted.
  }
  if (!alreadyPrompted) {
    window.setTimeout(() => {
      if ("Notification" in window && Notification.permission !== "default") return;
      if (!notificationPrompt.open) notificationPrompt.showModal();
      try {
        window.localStorage.setItem("family-circle-notification-prompted", "yes");
      } catch (error) {
        // No persistence is needed for permission to work.
      }
    }, 900);
  }
}

const paymentSuccess = document.querySelector(".toast.payment-success");
if (paymentSuccess) {
  const paymentOverlay = document.createElement("section");
  const spent = paymentSuccess.classList.contains("spent");
  paymentOverlay.className = "payment-confirmation";
  paymentOverlay.setAttribute("role", "status");
  const paymentCheck = document.createElement("div");
  paymentCheck.className = "payment-check";
  paymentCheck.appendChild(document.createElement("span"));
  const paymentHeading = document.createElement("p");
  paymentHeading.textContent = spent ? "Spend requested" : "Sent successfully";
  const paymentMessage = document.createElement("strong");
  paymentMessage.textContent = paymentSuccess.textContent;
  const paymentDetail = document.createElement("small");
  paymentDetail.textContent = spent ? "Reserved until Dad verifies the purchase" : "Your family payment is complete";
  paymentOverlay.append(paymentCheck, paymentHeading, paymentMessage, paymentDetail);
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

document.querySelectorAll("[data-go-back]").forEach((button) => {
  button.addEventListener("click", () => {
    if (window.history.length > 1) {
      window.history.back();
      return;
    }
    window.location.href = button.dataset.fallbackUrl || "/";
  });
});

const messageThread = document.querySelector("[data-message-thread]");
if (messageThread) {
  messageThread.scrollTop = messageThread.scrollHeight;
}
document.querySelectorAll(".ios-composer textarea").forEach((field) => {
  field.addEventListener("input", () => {
    field.style.height = "auto";
    field.style.height = `${Math.min(field.scrollHeight, 104)}px`;
  });
});
const conversationRefresh = document.querySelector("[data-refresh-conversations]");
if (conversationRefresh) {
  const status = document.querySelector("[data-refresh-status]");
  conversationRefresh.addEventListener("click", () => {
    conversationRefresh.disabled = true;
    conversationRefresh.classList.add("refreshing");
    if (status) status.textContent = "Checking for new messages...";
    window.setTimeout(() => window.location.reload(), 240);
  });
}

const messagingApp = document.querySelector("[data-incoming-call-url]");
if (messagingApp) {
  const banner = messagingApp.querySelector("[data-incoming-call-banner]");
  async function pollIncomingCall() {
    try {
      const response = await fetch(messagingApp.dataset.incomingCallUrl, {headers: {"Accept": "application/json"}});
      if (!response.ok) return;
      const {call} = await response.json();
      if (!call) return;
      banner.classList.remove("hidden");
      banner.innerHTML = "";
      const pulse = document.createElement("span");
      pulse.className = "incoming-pulse";
      const copy = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = `Incoming ${call.type.toLowerCase()} call`;
      const detail = document.createElement("small");
      detail.textContent = `${call.caller} is calling...`;
      copy.append(title, detail);
      const link = document.createElement("a");
      link.href = call.url;
      link.textContent = "Answer";
      banner.append(pulse, copy, link);
    } catch (error) {
      // Poll again later if the connection briefly drops.
    }
  }
  pollIncomingCall();
  window.setInterval(pollIncomingCall, 4000);
}

const watchedCallScreen = document.querySelector("[data-watch-call='yes']");
if (watchedCallScreen) {
  let callFinished = false;
  async function pollCallStatus() {
    if (callFinished) return;
    try {
      const response = await fetch(watchedCallScreen.dataset.statusUrl, {headers: {"Accept": "application/json"}});
      if (!response.ok) return;
      const {status, reason} = await response.json();
      if (status !== "declined" && status !== "ended") return;
      callFinished = true;
      const message = reason === "schedule" ? "Calling hours are over." : (status === "declined" ? "Call declined." : "Call ended.");
      toast(message);
      window.setTimeout(() => {
        window.location.href = watchedCallScreen.dataset.returnUrl;
      }, 700);
    } catch (error) {
      // The next poll will retry if the network briefly drops.
    }
  }
  pollCallStatus();
  window.setInterval(pollCallStatus, 2000);
}

const callScreen = document.querySelector("[data-livekit-call='join']");
if (callScreen) {
  const waiting = callScreen.querySelector("[data-call-waiting]");
  const remoteVideo = callScreen.querySelector("[data-remote-video]");
  const localVideo = callScreen.querySelector("[data-local-video]");
  let room;
  let microphoneEnabled = true;
  let cameraEnabled = callScreen.dataset.callType === "video";

  async function connectLiveKitCall() {
    try {
      const tokenResponse = await fetch(callScreen.dataset.tokenUrl, {headers: {"Accept": "application/json"}});
      const connection = await tokenResponse.json();
      if (!tokenResponse.ok) {
        if (tokenResponse.status === 409) {
          toast(connection.error || "Start a new call to reconnect.");
          window.setTimeout(() => {
            window.location.href = callScreen.dataset.returnUrl;
          }, 800);
          return;
        }
        throw new Error(connection.error || "Could not join the call.");
      }
      const {Room, RoomEvent, Track} = await import("https://cdn.jsdelivr.net/npm/livekit-client@2.15.7/+esm");
      room = new Room({adaptiveStream: true, dynacast: true});
      room.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind === Track.Kind.Video) {
          track.attach(remoteVideo);
          waiting.classList.add("hidden");
        } else {
          const audioElement = track.attach();
          audioElement.hidden = true;
          callScreen.appendChild(audioElement);
        }
      });
      await room.connect(connection.wsUrl, connection.token);
      await room.localParticipant.setMicrophoneEnabled(true);
      if (cameraEnabled) {
        const publication = await room.localParticipant.setCameraEnabled(true);
        const track = publication && publication.track;
        if (track && localVideo) track.attach(localVideo);
      }
    } catch (error) {
      toast(error.message || "Could not connect the family call.");
    }
  }

  callScreen.querySelector("[data-toggle-mic]")?.addEventListener("click", async (event) => {
    microphoneEnabled = !microphoneEnabled;
    await room?.localParticipant.setMicrophoneEnabled(microphoneEnabled);
    event.currentTarget.textContent = microphoneEnabled ? "Mute" : "Unmute";
  });
  callScreen.querySelector("[data-toggle-camera]")?.addEventListener("click", async (event) => {
    cameraEnabled = !cameraEnabled;
    await room?.localParticipant.setCameraEnabled(cameraEnabled);
    event.currentTarget.textContent = cameraEnabled ? "Camera" : "Camera Off";
  });
  callScreen.querySelector("[data-end-call]")?.addEventListener("submit", () => room?.disconnect());
  window.addEventListener("pagehide", () => room?.disconnect());
  connectLiveKitCall();
}

const guardianOS = document.querySelector("[data-guardian-os]");
if (guardianOS) {
  const homeScreen = guardianOS.querySelector("[data-guardian-home]");
  const appPages = Array.from(guardianOS.querySelectorAll(".guardian-native-app[data-parent-app]"));
  const appTriggers = Array.from(guardianOS.querySelectorAll("[data-parent-open]"));
  const baseURL = `${window.location.pathname}${window.location.search}`;
  const selectedChild = guardianOS.dataset.selectedChild || "default";
  const appMemoryKey = `family-circle-parent-app-${selectedChild}`;

  // Keep focused create/edit sheets usable from any native parent app.
  guardianOS.querySelectorAll(".guardian-native-app dialog").forEach((dialog) => guardianOS.appendChild(dialog));

  function showParentHome(updateURL) {
    if (homeScreen) homeScreen.hidden = false;
    appPages.forEach((page) => page.classList.remove("active"));
    guardianOS.classList.remove("parent-app-open");
    appTriggers.forEach((trigger) => trigger.removeAttribute("aria-current"));
    try {
      window.sessionStorage.removeItem(appMemoryKey);
    } catch (error) {
      // The parent home remains available even when browser storage is restricted.
    }
    if (updateURL) window.history.replaceState({}, "", baseURL);
    window.scrollTo({top: 0, behavior: "smooth"});
  }

  function openParentApp(name, updateURL) {
    const page = appPages.find((candidate) => candidate.dataset.parentApp === name);
    if (!page) return;
    if (homeScreen) homeScreen.hidden = true;
    appPages.forEach((candidate) => candidate.classList.toggle("active", candidate === page));
    guardianOS.classList.add("parent-app-open");
    appTriggers.forEach((trigger) => {
      if (trigger.dataset.parentOpen === name) trigger.setAttribute("aria-current", "page");
      else trigger.removeAttribute("aria-current");
    });
    try {
      window.sessionStorage.setItem(appMemoryKey, name);
    } catch (error) {
      // A page refresh returns home when browser storage is restricted.
    }
    if (updateURL) window.history.pushState({parentApp: name}, "", `${baseURL}#parent-${name}`);
    window.scrollTo({top: 0, behavior: "smooth"});
  }

  appTriggers.forEach((trigger) => trigger.addEventListener("click", () => openParentApp(trigger.dataset.parentOpen, true)));
  guardianOS.querySelectorAll("[data-parent-home-button]").forEach((button) => {
    button.addEventListener("click", () => showParentHome(true));
  });
  window.addEventListener("popstate", () => {
    const appName = window.location.hash.replace("#parent-", "");
    if (appName && window.location.hash.startsWith("#parent-")) openParentApp(appName, false);
    else showParentHome(false);
  });

  const initialApp = window.location.hash.replace("#parent-", "");
  let rememberedApp = "";
  try {
    rememberedApp = window.sessionStorage.getItem(appMemoryKey) || "";
  } catch (error) {
    // No remembered app is required to use the parent dashboard.
  }
  if (initialApp && window.location.hash.startsWith("#parent-")) openParentApp(initialApp, false);
  else if (rememberedApp) openParentApp(rememberedApp, false);
}

document.querySelectorAll("[data-auto-open-dialog]").forEach((dialog) => {
  if (dialog.showModal) dialog.showModal();
});

document.querySelectorAll("[data-confirm-deduction]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm("Remove these tokens for the recorded behavior reason?")) event.preventDefault();
  });
});
document.querySelectorAll("[data-confirm-punishment-removal]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm("Remove this punishment and record the correction?")) event.preventDefault();
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
