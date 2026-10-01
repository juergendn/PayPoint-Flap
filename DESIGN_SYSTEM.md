# Design-System – „MinervaTec / WMS" Dark Dashboard

Wiederverwendbare Beschreibung des Frontend-Designs. Ziel: In einem neuen Projekt
das gleiche Look-and-Feel ohne externes CSS-Framework reproduzieren.
Stack-neutral – funktioniert mit Flask/Jinja, aber genauso mit jedem anderen
Server-/Frontend-Framework (nur HTML + CSS + Vanilla-JS, keine Build-Tools).

---

## 1. Designphilosophie

- **Dark-First.** Tiefdunkler GitHub-artiger Hintergrund (`#0d1117`), darüber
  leicht erhellte Panels. Ein **helles Theme** ist optional zuschaltbar:
  `[data-theme="light"]` auf `<html>` überschreibt nur die Design-Tokens
  (GitHub-Light-Palette), Umschalter in der Topbar, Wahl im Cookie `mvt_theme`
  (serverseitig gerendert, kein Aufblitzen). Dunkel bleibt der Standard.
- **Tech / „Sci-Fi"-Akzent.** Überschriften, Tabellenköpfe, Navigations-Gruppen
  und Uhrzeit nutzen die Display-Schrift **Audiowide**. Fließtext bleibt in der
  neutralen System-Schrift.
- **Ein blauer Akzent** (`#1f6feb`) trägt die ganze UI. Status wird ausschließlich
  über Grün/Rot/Gelb kommuniziert.
- **Flach, aber plastisch.** Dünne 1px-Borders (`#30363d`) statt harter Schatten;
  Schatten nur dezent zur Tiefenstaffelung.
- **Keine Frameworks.** Ein einziges `style.css` mit CSS-Variablen + Utility-Klassen.
  Komponenten-Styles werden oft inline gesetzt, greifen aber immer auf die Variablen zu.
- **Layout = Topbar + Sidebar + Content.** Vollhöhe, Content scrollt, Chrome bleibt fix.
- **PWA-fähig & mobil.** Eigene Mobile-Templates, `manifest.json`, Service Worker,
  Desktop/Mobile-Umschalter pro Gerät (localStorage).

---

## 2. Design-Tokens (CSS-Variablen)

Das Herz des Systems. Alles referenziert diese Variablen – nie Hex-Werte direkt.

```css
:root {
    /* Hintergründe – von dunkel nach hell gestaffelt */
    --bg:       #0d1117;   /* Seitenhintergrund */
    --panel:    #161b22;   /* Karten, Topbar, Sidebar */
    --panel-2:  #1c2128;   /* Inputs, Tabellenkopf, Hover, vertiefte Flächen */

    /* Linien */
    --border:   #30363d;   /* alle Borders & Trenner */

    /* Text */
    --text:     #e6eef3;   /* Haupttext */
    --muted:    #8b949e;   /* Labels, Sekundärtext, Icons */

    /* Akzent */
    --accent:        #1f6feb;
    --accent-hover:  #388bfd;

    /* Akzent als Schriftfarbe: auf dunklen Panels heller als --accent, sonst
       schlecht lesbar. Im hellen Theme fällt er mit --accent zusammen. */
    --accent-text:   #58a6ff;

    /* Status */
    --success:  #3fb950;
    --error:    #f85149;   /* in manchem JS auch als --danger erwartet → Alias anlegen */
    --warning:  #d29922;

    /* Status als Schriftfarbe (hellere Varianten für dunklen Grund) */
    --success-text: #7ee787;
    --error-text:   #ff7b72;
    --warning-text: #e3b341;

    /* Farbschimmer im Seitenhintergrund (Kapitel 4) — als Token, damit das
       helle Theme sie abschwächen kann */
    --bg-glow-1: rgba(77,208,255,0.15);
    --bg-glow-2: rgba(255,126,219,0.2);

    /* UI-Skalierung (für Kiosk-/Tablet-Auflösungen) */
    --ui-scale: 1;
}
```

**Konventionen für Statusfarben:** Fläche = Farbe mit `0.1–0.2` Alpha, Border = Vollton,
Text = Vollton oder hellere Variante (z. B. Success-Text `#7ee787`, Error-Text `#ff7b72`).

> ⚠️ Manche JS-Snippets verwenden `var(--danger)`. Entweder konsequent `--error`
> nutzen **oder** zusätzlich `--danger: #f85149;` definieren, damit nichts ins
> Leere zeigt.

---

## 2a. Helles Theme (Umschaltung dunkel ⇄ hell)

Dunkel bleibt der Standard, hell ist zuschaltbar. Weil **alles** über die Tokens
aus Kapitel 2 läuft, ist das helle Theme ein einziger Override-Block — kein
zweites Stylesheet, keine Klassen an Komponenten:

```css
/* Umgeschaltet über data-theme auf <html>. KEIN Attribut = dunkel (Standard). */
[data-theme="light"] {
    --bg: #f6f8fa;
    --panel: #ffffff;
    --panel-2: #eff2f5;
    --border: #d0d7de;
    --text: #1f2328;
    --muted: #59636e;
    --accent: #0969da;
    --accent-hover: #0550ae;
    --accent-text: #0969da;      /* fällt mit --accent zusammen */
    --success: #1a7f37;
    --error: #cf222e;
    --danger: #cf222e;
    --warning: #9a6700;
    --success-text: #1a7f37;     /* die *-text-Varianten kollabieren auf den */
    --error-text: #cf222e;       /* Vollton: auf Weiß ist der lesbar, die    */
    --warning-text: #9a6700;     /* hellen Dark-Varianten wären es nicht     */
    --bg-glow-1: rgba(9,105,218,0.07);   /* Glows nur noch als Hauch */
    --bg-glow-2: rgba(191,57,137,0.05);
}
```

Palette = **GitHub Light** (Gegenstück zur GitHub-Dark-Basis). Wichtig: die
Statusfarben sind im hellen Theme **dunkler** als im dunklen (z. B. Warning
`#d29922` → `#9a6700`), weil sie dort als Text auf hellen Flächen stehen.

### Zustand: Cookie + Attribut, serverseitig gerendert (kein Aufblitzen)

Die Wahl liegt im Cookie `mvt_theme` (`light`/`dark`, 1 Jahr, `SameSite=Lax`).
Der Server rendert das Attribut **direkt ins HTML** — würde erst JS nach dem
Laden umschalten, blitzte bei jedem Seitenwechsel das falsche Theme auf (FOUC):

```jinja
{% set theme_light = request.cookies.get('mvt_theme') == 'light' %}
<html lang="de"{% if theme_light %} data-theme="light"{% endif %}>
...
<meta name="theme-color" content="{{ '#f6f8fa' if theme_light else '#0d1117' }}">
```

`theme-color` färbt die Browser-/PWA-Chrome und muss je Theme mitwechseln —
serverseitig gerendert **und** beim Klick per JS nachgezogen.

### Umschalter (Topbar) + JS

Ein Button `.theme-toggle` in der Topbar (auf Auth-Seiten ohne Topbar:
`position: fixed` oben rechts). Icon zeigt das **Ziel**, nicht den Zustand
(dunkel aktiv → ☀️ „mach hell“). Kein Neuladen nötig — Attribut umschalten
reicht, weil alle Styles auf den Variablen hängen:

```js
function initThemeToggle() {
    var buttons = document.querySelectorAll('.theme-toggle');
    if (!buttons.length) return;
    var root = document.documentElement;
    function render() {
        var light = root.getAttribute('data-theme') === 'light';
        buttons.forEach(function (btn) {
            btn.textContent = light ? '🌙' : '☀️';
            btn.title = light ? 'Dunkles Design' : 'Helles Design';
        });
        var meta = document.querySelector('meta[name="theme-color"]');
        if (meta) meta.setAttribute('content', light ? '#f6f8fa' : '#0d1117');
    }
    buttons.forEach(function (btn) {
        btn.addEventListener('click', function () {
            var toLight = root.getAttribute('data-theme') !== 'light';
            if (toLight) root.setAttribute('data-theme', 'light');
            else root.removeAttribute('data-theme');   // Standard = kein Attribut
            document.cookie = 'mvt_theme=' + (toLight ? 'light' : 'dark') +
                '; path=/; max-age=31536000; SameSite=Lax';
            render();
        });
    });
    render();
}
```

### Logo je Theme (ohne JS)

Ein weißes/invertiertes Logo verschwindet auf hellem Grund. Lösung: **beide
Varianten rendern**, CSS blendet um — wirkt sofort beim Umschalten, ohne JS:

```html
<img class="brand-logo brand-logo-dark"  src="/static/logo-invertiert.svg" alt="Marke">
<img class="brand-logo brand-logo-light" src="/static/logo-fullcolor.svg"  alt="Marke">
```
```css
.brand-logo-light { display: none; }
[data-theme="light"] .brand-logo-dark  { display: none; }
[data-theme="light"] .brand-logo-light { display: block; }
```

### Stolperfallen (aus der Umstellung gelernt)

- **Halbtransparente rgba-Tönungen (Badges, Alerts, Hover-Tints) NICHT je Theme
  neu definieren.** Auf hellem Grund ergeben sie automatisch Pastellflächen —
  das ist gewollt und spart Dutzende Overrides. Nur dort eingreifen, wo der
  Kontrast wirklich kippt.
- **Punktuelle Kontrast-Fixes statt Flächen-Overrides.** Beispiel: eine Pille
  mit `background: var(--warning)` trägt im Dunklen dunkle Schrift (Warning ist
  helles Gelb), im Hellen ist `--warning` ein dunkles Gelb → dort weiße Schrift:
  `[data-theme="light"] .flag-badge.b1 { color: #fff; }`. Solche Fälle einzeln
  suchen (überall, wo Text **auf** einer Statusfarbe steht, nicht in ihr).
- **Eigenständige Seiten und iframes erben das Attribut nicht.** Fehlerseiten
  ohne Base-Template und Inhalte im `<iframe>` (das Eltern-`data-theme` greift
  im Frame-Dokument nicht) müssen das Cookie **selbst** lesen und das Attribut
  setzen.
- **Hex-Werte im Bestand aufspüren:** Die Umstellung funktioniert nur, wenn
  wirklich alles auf Tokens zeigt. Vorher `grep '#[0-9a-f]\{6\}'` über CSS und
  Templates — jeder direkte Hex-Wert ist ein Kandidat, der im anderen Theme
  falsch aussieht.
- **`background-color` als Fallback vor dem Gradient** (Kapitel 4) mitführen,
  sonst blitzt beim Umschalten kurz Weiß/Schwarz durch.

---

## 3. Typografie

```css
/* Fließtext: System-Stack, schnell & nativ */
font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;

/* Display: Headlines, Tabellenkopf, Nav-Gruppen, Uhr, Markenname */
font-family: 'Audiowide', sans-serif;
```

Einbindung (Google Fonts, mit Preconnect für Performance):

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Audiowide&display=swap" rel="stylesheet">
```

Regel:

```css
h1, h2, h3, h4, h5, h6, .brand-font {
    font-family: 'Audiowide', sans-serif;
    font-weight: normal;     /* Audiowide nur in einem Schnitt → nie bold setzen */
}
```

Richtwerte: Seitentitel `24px`, Marke `1.2rem`, Labels `0.9rem`,
Tabellenkopf `0.85rem`, Nav-Gruppen-Header `0.75rem` UPPERCASE, Badges `0.75rem`.

---

## 4. Hintergrund (Signature-Look)

Zwei farbige Radial-Glows (cyan + magenta) über dem dunklen Grundton – das
prägende, wiedererkennbare Detail. Fixiert, damit es beim Scrollen ruhig bleibt.
Die Glow-Farben sind Tokens (`--bg-glow-1/2`, Kapitel 2), damit das helle Theme
sie auf einen dezenten Hauch abschwächen kann statt sie zu verlieren.

```css
body {
    background-color: var(--bg);
    background: radial-gradient(circle at top,      var(--bg-glow-1), transparent 55%),
                radial-gradient(circle at 20% 20%,  var(--bg-glow-2), transparent 45%),
                var(--bg);
    background-attachment: fixed;
    color: var(--text);
}
```

---

## 5. Layout-Gerüst

Vollhöhe-Flex-Layout. Topbar oben fix, darunter horizontal Sidebar + scrollbarer Content.

```
┌─────────────────────────────────────────────┐
│  TOPBAR (90px, --panel, fix)                  │
├───────────┬─────────────────────────────────┤
│ SIDEBAR   │  CONTENT (.content, scrollt)      │
│ 250px     │                                   │
│ --panel   │  ┌── .card ──┐  ┌── .card ──┐      │
│ scrollt   │  │           │  │           │      │
│           │  └───────────┘  └───────────┘      │
│ [User]    │                                   │
│ [Uhr/VPN] │                                   │
└───────────┴─────────────────────────────────┘
```

```css
body { height: 100vh; display: flex; flex-direction: column; margin: 0; }

.app-container { display: flex; flex: 1; overflow: hidden; }

.topbar {
    height: 90px; flex-shrink: 0; z-index: 10;
    background-color: var(--panel);
    border-bottom: 1px solid var(--border);
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 20px;
}

.sidebar {
    width: 250px; flex-shrink: 0; height: 100%;
    background-color: var(--panel);
    border-right: 1px solid var(--border);
    display: flex; flex-direction: column; padding-top: 20px;
    overflow-y: auto; overscroll-behavior: contain; -webkit-overflow-scrolling: touch;
}

.content { flex: 1; padding: 20px; overflow-y: auto; }
```

**UI-Skalierung (optional, für Kiosk/Tablet).** Ein `.ui-scale`-Wrapper um den
gesamten Inhalt erlaubt es, die ganze UI über eine Variable zu verkleinern
(z. B. feste Tablet-Auflösungen):

```css
.ui-scale {
    transform: scale(var(--ui-scale));
    transform-origin: top left;
    width:  calc(100% / var(--ui-scale));
    height: calc(100% / var(--ui-scale));
    min-height: calc(100vh / var(--ui-scale));
}
@media (width: 810px) and (height: 1080px) { :root { --ui-scale: 0.5; } }
@media (width: 1080px) and (height: 810px) { :root { --ui-scale: 0.5; } }
```

---

## 6. Navigation (Sidebar)

Flache Links + **einklappbare Gruppen**. Aktiver Link bekommt einen Akzent-Balken links.

```css
.nav-link {
    display: flex; align-items: center;
    padding: 12px 20px;
    color: var(--muted); text-decoration: none;
    border-left: 3px solid transparent;
    transition: all 0.2s;
}
.nav-link:hover, .nav-link.active { background-color: var(--panel-2); color: var(--text); }
.nav-link.active { border-left-color: var(--accent); }
.nav-icon { margin-right: 10px; width: 20px; text-align: center; }   /* Emoji-Icons */

.nav-group-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 20px; margin-top: 10px;
    color: var(--muted); font-size: 0.75rem; font-weight: bold;
    text-transform: uppercase; font-family: 'Audiowide', sans-serif;
    cursor: pointer; user-select: none; transition: color 0.2s;
}
.nav-group-header:hover { color: var(--text); }
.nav-group-header::after { content: '▼'; font-size: 0.8em; transition: transform 0.2s; }
.nav-group-header.collapsed::after { transform: rotate(-90deg); }

.nav-group-content { overflow: hidden; max-height: 1000px; transition: max-height 0.3s ease-out; }
.nav-group-content.collapsed { max-height: 0; }

/* Untergruppe: Menüpunkt mit Unterpunkten INNERHALB einer Gruppe (z. B. „Rech./Liefers.").
   Nutzt denselben Klapp-Mechanismus (beide Klassen tragen!), sieht aber wie ein
   normaler Menüpunkt aus; Unterpunkte sind eingerückt. */
.nav-subgroup-header { margin-top: 0; padding: 12px 20px; font-family: inherit;
    font-size: inherit; text-transform: none; color: var(--muted);
    border-left: 3px solid transparent; }
.nav-subgroup-header:hover { background-color: var(--panel-2); color: var(--text); }
.nav-subgroup-content .nav-link { padding-left: 40px; }
```

**Icons = Emojis** (📊 🏢 🛠 🔧 ⚙️ …). Kein Icon-Font, keine SVG-Bibliothek nötig.

**Verhalten (Vanilla-JS):** Klick auf Header toggelt `.collapsed` auf Header + nächstem
`.nav-group-content`. Beim Laden werden alle Gruppen ohne aktiven Link automatisch eingeklappt:

```js
document.querySelectorAll('.nav-group-header').forEach(header => {
    header.addEventListener('click', function () {
        this.classList.toggle('collapsed');
        this.nextElementSibling?.classList.toggle('collapsed');
    });
});
document.querySelectorAll('.nav-group-content').forEach(content => {
    if (!content.querySelector('.active')) {   // Link ODER aktiver Ordnerknoten hält die Gruppe offen
        content.classList.add('collapsed');
        content.previousElementSibling?.classList.add('collapsed');
    }
});
```

**Oberste Ebene „Ablage" mit Live-Ordnerbaum.** Die Belegtypen (Rechnungen, Lieferscheine,
Dokumente, Neuer Beleg, Suche) und darunter der **echte, mandantenweite Ordnerbaum** liegen
gemeinsam in der obersten Gruppe `Ablage` (kein separates „Archiv" mehr). Der Baum wird pro
Request aus `folder_tree()` in den Template-Kontext gespeist (`nav_tree`), rekursiv als
verschachtelte `<ul class="folder-tree">` gerendert; jeder Knoten ist ein Link auf
`/ordner?fid=…` mit Dokumentanzahl-Badge. Teilbäume sind per Default **zugeklappt** (Caret
`▸`/`▾`), der Pfad zum aktiven Ordner wird per JS aufgeklappt; `max-height` der Gruppe auf
`3000px` erhöht, damit tiefe Bäume nicht abgeschnitten werden.

Unten in der Sidebar (per `margin-top: auto` nach unten geschoben): User-Block
(Name, Passwort/Passkey/Logout) und ein Info-Block mit Live-Datum/-Uhr, Version +
Changelog-Badge, VPN-Statuspunkt und Desktop/Mobile-Toggle.

---

## 7. Komponenten

### Karten
```css
.card {
    background-color: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 20px; margin-bottom: 20px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}
```

### Dashboard-Grid (auto-responsive, ohne Media Queries)
```css
.dashboard-grid {
    display: grid; gap: 20px; align-items: start;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
}
.dashboard-card { min-width: 0; }
.dashboard-card .table-responsive { overflow-x: auto; }
```

### Buttons
Basis + Varianten. Solide für Primäraktionen, **Outline** für alles andere
(eine Outline-Variante je Statusfarbe).

```css
.btn {
    display: inline-block; padding: 8px 16px; border-radius: 6px;
    border: none; cursor: pointer; font-family: inherit; font-weight: 500;
    text-decoration: none; transition: background-color 0.2s;
}
.btn-primary   { background-color: var(--accent); color: #fff; }
.btn-primary:hover { background-color: var(--accent-hover); }
.btn-secondary { background-color: var(--panel-2); color: var(--text); border: 1px solid var(--border); }
.btn-secondary:hover { background-color: var(--border); }
.btn-danger    { background: transparent; border: 1px solid var(--error); color: var(--error); }
.btn-danger:hover { background-color: rgba(248,81,73,0.1); }

/* Outline-Familie: transparent + 1px Border + Hover-Tint (Farbe @ 0.1 Alpha) */
.btn-outline-primary { background: transparent; color: var(--accent);  border: 1px solid var(--accent); }
.btn-outline-danger  { background: transparent; color: var(--error);   border: 1px solid var(--error); }
.btn-outline-success { background: transparent; color: var(--success); border: 1px solid var(--success); }
.btn-outline-warning { background: transparent; color: var(--warning); border: 1px solid var(--warning); }
.btn-outline-info    { background: transparent; color: var(--text);    border: 1px solid var(--muted); }
.btn-outline-primary:hover { background-color: rgba(31,111,235,0.1); }
.btn-outline-danger:hover  { background-color: rgba(248,81,73,0.1); }
.btn-outline-success:hover { background-color: rgba(63,185,80,0.1); }
.btn-outline-warning:hover { background-color: rgba(210,153,34,0.1); }
.btn-outline-info:hover    { background-color: rgba(139,148,158,0.1); }

.btn-sm { padding: 4px 8px; font-size: 0.85em; }
```

### Formulare
Labels in `--muted`, Felder auf `--panel-2`, Fokus = Akzent-Border (kein Outline-Ring).

```css
.form-group { margin-bottom: 15px; }
label { display: block; margin-bottom: 8px; color: var(--muted); font-size: 0.9rem; }
input, select {
    width: 100%; padding: 10px; box-sizing: border-box;
    background-color: var(--panel-2); border: 1px solid var(--border);
    border-radius: 6px; color: var(--text); font-family: inherit;
}
input:focus, select:focus { outline: none; border-color: var(--accent); }

/* iOS: >=16px verhindert Auto-Zoom beim Fokussieren */
@media (max-width: 768px) { input, select, textarea { font-size: 16px; } }
```

### Tabellen
Volle Breite, Tabellenkopf in `--panel-2` + Audiowide, Zeilen-Hover.

```css
table { width: 100%; border-collapse: collapse; }
th {
    text-align: left; padding: 12px;
    background-color: var(--panel-2); color: var(--muted);
    font-family: 'Audiowide', sans-serif; font-size: 0.85rem;
    border-bottom: 1px solid var(--border);
}
td { padding: 12px; border-bottom: 1px solid var(--border); color: var(--text); }
tr:hover td { background-color: var(--panel-2); }
```

### Badges & Alerts (Status-Pattern)
```css
.badge { padding: 4px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: bold; }
.badge-success { background: rgba(63,185,80,0.2);  color: var(--success); border: 1px solid var(--success); }
.badge-error   { background: rgba(248,81,73,0.2);  color: var(--error);   border: 1px solid var(--error); }
.badge-warning { background: rgba(210,153,34,0.2); color: var(--warning); border: 1px solid var(--warning); }

.alert { padding: 10px 15px; border-radius: 6px; margin-bottom: 15px; }
.alert-success { background: rgba(63,185,80,0.1); border: 1px solid var(--success); color: var(--success); }
.alert-error   { background: rgba(248,81,73,0.1); border: 1px solid var(--error);   color: var(--error); }
```

### Status-Punkt (z. B. Online/VPN)
```css
.status-dot {
    width: 10px; height: 10px; border-radius: 50%;
    background-color: var(--success);
    box-shadow: 0 0 8px var(--success);   /* leuchtet */
}
```

### Flash-/Toast-Meldungen
Zentriert eingeblendet, halbtransparent gefärbt, mit Glow-Schatten,
nach 3 s per JS ausgeblendet.

```css
.flash-message { padding: 20px; margin-bottom: 10px; border-radius: 8px; font-weight: 500; text-align: center; }
.flash-success { background: rgba(63,185,80,0.95);  border: 1px solid var(--success); color: #7ee787; box-shadow: 0 4px 20px rgba(63,185,80,0.3); }
.flash-error   { background: rgba(248,81,73,0.95);  border: 1px solid var(--error);   color: #ff7b72; box-shadow: 0 4px 20px rgba(248,81,73,0.3); }
.flash-warning { background: rgba(210,153,34,0.95); border: 1px solid var(--warning); color: #e3b341; box-shadow: 0 4px 20px rgba(210,153,34,0.3); }
```
Container: `position: fixed; top/left 50%; transform: translate(-50%,-50%); z-index: 9999;`

### Utilities
```css
.text-muted { color: var(--muted); }
.mt-4 { margin-top: 1.5rem; }
.mb-4 { margin-bottom: 1.5rem; }
```

---

## 8. Modal-Muster

Kein Modal-Plugin – ein gefärbtes Overlay + zentrierte Panel-Box, per JS
`display` umgeschaltet. Schließen-`×` oben rechts, Akzent-Titel.

```html
<div id="myModal" style="display:none; position:fixed; inset:0;
     background:rgba(0,0,0,0.7); z-index:2000; align-items:center; justify-content:center;">
  <div style="background:var(--panel); width:90%; max-width:700px; padding:24px;
       border-radius:8px; border:1px solid var(--border); position:relative;">
    <button onclick="document.getElementById('myModal').style.display='none'"
            style="position:absolute; top:12px; right:12px; background:none; border:none;
                   color:var(--text); font-size:1.5rem; cursor:pointer;">&times;</button>
    <h3 style="margin-top:0; color:var(--accent);">Titel</h3>
    <!-- Inhalt -->
  </div>
</div>
```
Öffnen mit `display:'flex'` (zentriert) bzw. `display:'block'` (Variante mit `margin:100px auto`).

---

## 9. Mobile & PWA

- **Eigene Mobile-Templates** statt reiner Responsive-Breakpoints. Topbar wird über
  `.topbar.mobile-header` umgebaut (zentriert, mehrzeilig), Sidebar wird leer gelassen.
- **Großflächige Touch-Buttons:** volle Breite, `padding: 14–15px`, `border-radius: 8px`,
  zentriert. Primäraktion oft `var(--success)` mit `color: var(--bg)`.
- **Fixierte Zurück-Aktion / Bottom-Padding:**
  ```css
  .mobile-header  { justify-content:center; height:auto; min-height:70px; flex-direction:column; padding:10px; gap:6px; }
  .mobile-back    { position:fixed; left:16px; bottom:16px; z-index:1000; }
  .mobile-content { padding-bottom:80px; }
  ```
- **Desktop/Mobile-Umschalter** merkt die Wahl pro Gerät in `localStorage`
  (`wms_view_mode = desktop|mobile`) und leitet entsprechend um.

**PWA-Setup** (`manifest.json`) – Theme-Farbe = Hintergrundton, damit die App nahtlos wirkt:
```json
{
  "name": "App Name", "short_name": "App",
  "display": "standalone",
  "background_color": "#0d1117",
  "theme_color": "#0d1117",
  "icons": [{ "src": "logo.svg", "sizes": "any", "type": "image/svg+xml" }]
}
```
Im `<head>`:
```html
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="manifest" href="/static/manifest.json">
<link rel="icon" type="image/svg+xml" href="/static/logomark.svg">
```

---

## 10. Wiederkehrende JS-Bausteine (Vanilla, kein Framework)

- **Live-Datum/-Uhr** in der Sidebar, `setInterval(updateDateTime, 1000)`,
  `toLocaleDateString('de-DE', …)` – Uhr in Audiowide.
- **Auto-Ausblenden** von Flash-Meldungen nach 3 s.
- **`DataCache`** – kleiner `sessionStorage`-Cache vor `fetch` mit TTL +
  `evict(pattern)` zum gezielten Invalidieren.
- **Statuspolling** (z. B. VPN/Erreichbarkeit) mit `AbortController`-Timeout,
  Statuspunkt + Text werden live umgefärbt.

Diese Bausteine sind optional – das Design steht auch ohne sie.

---

## 11. Schnellstart für ein neues Projekt

1. `style.css` aus den Kapiteln 2–7 zusammensetzen (oder das vorhandene `static/style.css`
   1:1 übernehmen – es ist framework-frei und projektneutral).
2. Audiowide + Preconnect-Links in den `<head>`.
3. Body-Gradient (Kapitel 4) setzen.
4. Layout-Gerüst aufbauen:

```html
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Audiowide&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <div class="ui-scale">
    <header class="topbar">
      <a href="#" class="brand brand-font"><div class="status-dot"></div> Markenname</a>
      <div class="page-title brand-font" style="flex:1; text-align:center;">Bereich</div>
      <div class="user-menu">…</div>
    </header>

    <div class="app-container">
      <nav class="sidebar">
        <a href="#" class="nav-link active"><span class="nav-icon">📊</span> Dashboard</a>
        <div class="nav-group-header">Bereich</div>
        <div class="nav-group-content">
          <a href="#" class="nav-link"><span class="nav-icon">🔧</span> Unterpunkt</a>
        </div>
        <!-- unten: User-/Info-Block mit margin-top:auto -->
      </nav>

      <main class="content">
        <div class="dashboard-grid">
          <div class="card dashboard-card">…</div>
        </div>
      </main>
    </div>
  </div>
</body>
</html>
```

5. Pro Seite: `card`, `btn-*`, `badge-*`, `alert-*`, Tabellen-Styles nutzen.
   Statusfarben immer nach dem Muster *Fläche @0.1–0.2 / Border Vollton / Text Vollton*.

---

## 12. Checkliste „so fühlt es sich richtig an"

- [ ] Hintergrund hat den cyan+magenta Doppel-Glow, `background-attachment: fixed`.
- [ ] Überschriften, Tabellenkopf, Nav-Gruppen, Uhr in **Audiowide** (`font-weight: normal`).
- [ ] Genau **ein** blauer Akzent; aktiver Nav-Link hat 3px Akzent-Balken links.
- [ ] Panels gestaffelt: `--bg` < `--panel` < `--panel-2`; Borders immer `--border`.
- [ ] Buttons: solide nur primär, sonst Outline-Familie mit Hover-Tint.
- [ ] Status nur über Grün/Rot/Gelb, immer nach dem Alpha/Border/Text-Muster.
- [ ] Inputs auf `--panel-2`, Fokus = Akzent-Border statt Outline-Ring.
- [ ] Icons sind Emojis, keine Icon-Bibliothek.
- [ ] Mobil: volle-Breite-Touch-Buttons, eigenes Mobile-Template, PWA-Manifest mit `#0d1117`.
- [ ] Helles Theme: reiner Token-Override über `[data-theme="light"]`, Cookie
      serverseitig gerendert (kein Aufblitzen), `meta theme-color` wechselt mit,
      Logo je Theme per CSS umgeblendet (Kapitel 2a).
```

---

*Referenz-Implementierung: `static/style.css`, `templates/base.html`, `templates/login.html`,
`templates/mobile_start.html`, `static/manifest.json`.*
