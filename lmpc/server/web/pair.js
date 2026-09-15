/* Pairing page: say "connected" when a phone enrolls, without making the user reload.
   Polls a loopback-only endpoint; stops as soon as the tab is hidden. */
(function () {
  "use strict";
  var status = document.getElementById("status");
  if (!status || status.dataset.open !== "true") return;

  var seen = 0;
  var timer = null;

  function paint(state) {
    var n = state.devices_enrolled || 0;
    if (n > seen) {
      seen = n;
      status.dataset.connected = "true";
      status.textContent = n === 1
        ? "Phone connected. Scan again to add another."
        : n + " phones connected. Scan again to add another.";
    }
  }

  function poll() {
    fetch("/pair/status", { headers: { "Accept": "application/json" } })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (state) { if (state) paint(state); })
      .catch(function () { /* the server is restarting; the next tick retries */ });
  }

  function start() { if (!timer) timer = setInterval(poll, 2000); }
  function stop() { clearInterval(timer); timer = null; }

  document.addEventListener("visibilitychange", function () {
    document.hidden ? stop() : start();
  });
  start();
}());
