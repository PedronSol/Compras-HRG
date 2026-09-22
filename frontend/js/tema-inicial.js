// Executado de forma síncrona no <head> para aplicar o tema antes da primeira pintura (sem "flash").
(function () {
  try {
    var tema = localStorage.getItem("rg-tema");
    if (tema === "light" || tema === "dark") document.documentElement.setAttribute("data-theme", tema);
    if (localStorage.getItem("rg-sidebar") === "recolhida") document.documentElement.setAttribute("data-sidebar", "recolhida");
  } catch (e) { /* armazenamento indisponível */ }
})();
