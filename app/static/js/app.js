// Umschalter hell/dunkel (DESIGN_SYSTEM.md, Kapitel 2a). Das Icon zeigt das Ziel.
// Die Wahl liegt im Cookie, der Server rendert sie direkt (kein Aufblitzen).
(function () {
  var buttons = document.querySelectorAll(".theme-toggle");
  if (!buttons.length) return;
  var root = document.documentElement;
  function render() {
    var light = root.getAttribute("data-theme") === "light";
    buttons.forEach(function (btn) {
      btn.textContent = light ? "🌙" : "☀️";
      btn.title = light ? "Dunkles Design" : "Helles Design";
    });
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", light ? "#f6f8fa" : "#0d1117");
  }
  buttons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var toLight = root.getAttribute("data-theme") !== "light";
      if (toLight) root.setAttribute("data-theme", "light");
      else root.removeAttribute("data-theme");
      document.cookie =
        "mvt_theme=" + (toLight ? "light" : "dark") + "; path=/; max-age=31536000; SameSite=Lax";
      render();
    });
  });
  render();
})();
