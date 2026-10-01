// Kiosk-Display: Live-Ereignisse vom Leser, Display-Sitzung, Inaktivität, Tastatur.
// Bildschirme kommen als HTMX-Fragmente vom Server; hier nur das Drumherum.
(function () {
  "use strict";
  var TIMEOUT_MS = (window.DISPLAY_TIMEOUT_S || 60) * 1000;
  var MELDUNG_MS = 6000;
  var token = null; // Display-Sitzung (nur nach Chip der Wäscheabteilung)
  var letzteAktivitaet = Date.now();
  var overlayTimer;

  function zeigen(url, methode) {
    htmx.ajax(methode || "GET", url, { target: "#bildschirm", swap: "innerHTML" });
  }

  function zurStartseite() {
    token = null;
    zeigen("/display/start");
  }

  // Jede Anfrage trägt das Token; abgelaufene Sitzung → Startseite.
  document.body.addEventListener("htmx:configRequest", function (e) {
    if (token) e.detail.headers["X-Display-Token"] = token;
  });
  document.body.addEventListener("htmx:responseError", function (e) {
    if (e.detail.xhr.status === 401 || e.detail.xhr.status === 403) zurStartseite();
  });

  // ---------- Inaktivität ----------

  function aktiv() {
    letzteAktivitaet = Date.now();
  }
  ["pointerdown", "keydown"].forEach(function (art) {
    document.addEventListener(art, aktiv, { passive: true });
  });
  setInterval(function () {
    var rest = document.getElementById("rest");
    if (!token) return;
    var uebrig = TIMEOUT_MS - (Date.now() - letzteAktivitaet);
    if (rest) rest.textContent = Math.max(0, Math.ceil(uebrig / 1000)) + " s";
    if (uebrig <= 0) {
      zeigen("/display/ende", "POST");
      token = null;
    }
  }, 1000);

  // ---------- Meldungen auf Chip ----------

  function meldungText(m) {
    var hallo = m.name ? "Hallo " + m.name + "\n" : "";
    switch (m.art) {
      case "abholung": return ["ok", hallo + "Fach " + m.fach + " ist offen"];
      case "kein_fach": return ["info", hallo + "Für dich liegt nichts bereit"];
      case "noch_nicht_bereit": return ["info", hallo + "Fach " + m.fach + " wird noch befüllt"];
      case "fach_gesperrt": return ["fehler", hallo + "Fach " + m.fach + " ist gesperrt – bitte Wäscheabteilung"];
      case "angelernt": return ["ok", "Chip " + m.kennung + " angelernt" + (m.name ? "\nfür " + m.name : "")];
      case "unbekannt": return ["fehler", "Chip unbekannt"];
      case "nicht_zugeordnet": return ["fehler", "Chip noch keinem Mitarbeiter zugeordnet"];
      case "gesperrt": return ["fehler", "Chip gesperrt"];
      default: return ["fehler", hallo + (m.text || "Störung – bitte Wäscheabteilung")];
    }
  }

  function overlay(art, text, danach) {
    var o = document.getElementById("overlay");
    var t = document.getElementById("overlay-text");
    t.className = "overlay-text " + art;
    t.textContent = text;
    o.hidden = false;
    clearTimeout(overlayTimer);
    overlayTimer = setTimeout(function () {
      o.hidden = true;
      if (danach) danach();
    }, MELDUNG_MS);
  }
  document.getElementById("overlay").addEventListener("click", function () {
    clearTimeout(overlayTimer);
    this.hidden = true;
    if (token) zeigen("/display/menue");
  });

  new EventSource("/events").addEventListener("chip", function (e) {
    var m = JSON.parse(e.data);
    aktiv();
    if (m.art === "menue") {
      token = m.token;
      document.getElementById("overlay").hidden = true;
      zeigen("/display/menue");
      return;
    }
    var t = meldungText(m);
    if (m.art === "angelernt" && token) {
      overlay(t[0], t[1], function () { zeigen("/display/menue"); });
      return;
    }
    // Jeder andere Chip beendet serverseitig eine offene Sitzung.
    if (token) zurStartseite();
    overlay(t[0], t[1]);
  });

  // ---------- Bildschirmtastatur ----------

  document.addEventListener("click", function (e) {
    var taste = e.target.closest("[data-taste]");
    if (taste) {
      var feld = document.getElementById("eingabe");
      var w = taste.getAttribute("data-taste");
      if (w === "ZURUECK") feld.value = feld.value.slice(0, -1);
      else if (w === "LEER") feld.value = "";
      else if (feld.value.length < 40) feld.value += w;
      feld.dispatchEvent(new Event("input", { bubbles: true }));
      return;
    }
    var umschalter = e.target.closest("[data-tastatur]");
    if (umschalter) {
      var ziel = umschalter.getAttribute("data-tastatur");
      document.querySelectorAll("[data-tastenfeld]").forEach(function (f) {
        f.hidden = f.getAttribute("data-tastenfeld") !== ziel;
      });
      document.querySelectorAll("[data-tastatur]").forEach(function (b) {
        b.classList.toggle("aktiv", b === umschalter);
      });
    }
  });
})();
