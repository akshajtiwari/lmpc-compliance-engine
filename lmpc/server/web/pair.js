/* Pairing page: report what is happening without making the officer reload.

   Two things change under the page. A phone finishing enrolment, and a phone reaching
   this computer at all — including being refused, which is the case worth surfacing
   loudest, because it means the address is right and only the switch is in the way.
   Polls a loopback-only endpoint; stops as soon as the tab is hidden. */
(function () {
  "use strict";
  var status = document.getElementById("status");
  var contact = document.getElementById("contact");
  if (!status && !contact) return;

  var seen = 0;
  var timer = null;

  function paintEnrolled(state) {
    if (!status || status.dataset.open !== "true") return;
    var n = state.devices_enrolled || 0;
    if (n > seen) {
      seen = n;
      status.dataset.connected = "true";
      status.textContent = n === 1
        ? "Phone connected. Scan again to add another."
        : n + " phones connected. Scan again to add another.";
    }
  }

  function ago(seconds) {
    if (seconds < 5) return "just now";
    if (seconds < 90) return seconds + " seconds ago";
    return Math.floor(seconds / 60) + " minutes ago";
  }

  function paintContact(state) {
    if (!contact) return;
    var seen_at = state.last_contact;
    if (!seen_at) return;
    var when = ago(seen_at.seconds_ago || 0);
    contact.className = "contact " + (seen_at.allowed ? "good" : "warn-text");
    contact.textContent = seen_at.allowed
      ? "A device at " + seen_at.peer + " reached this computer " + when + "."
      : "A device at " + seen_at.peer + " reached this computer " + when
        + " and was refused — allow phone connections above.";
  }

  function poll() {
    fetch("/pair/status", { headers: { "Accept": "application/json" } })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (state) { if (state) { paintEnrolled(state); paintContact(state); } })
      .catch(function () { /* the server is restarting; the next tick retries */ });
  }

  function start() { if (!timer) timer = setInterval(poll, 2000); }
  function stop() { clearInterval(timer); timer = null; }

  document.addEventListener("visibilitychange", function () {
    document.hidden ? stop() : start();
  });
  start();
}());
