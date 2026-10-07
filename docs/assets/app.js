// JS vanilla: drawer mobile + busca da sidebar (redireciona p/ search.html)
(function () {
  var btn = document.getElementById('menuBtn');
  var side = document.getElementById('sidebar');
  if (btn && side) btn.addEventListener('click', function () { side.classList.toggle('open'); });
  var s = document.getElementById('sideSearch');
  if (s) s.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      var base = location.pathname.includes('/pagina/') || location.pathname.includes('/categorias/') ? '../search.html' : 'search.html';
      location.href = base + '?q=' + encodeURIComponent(s.value.trim());
    }
  });
  // Reescreve links /wiki/X internos que sobraram no HTML das seções
  document.querySelectorAll('a[href^="/wiki/"]').forEach(function (a) {
    var parte = a.getAttribute('href').split('/wiki/')[1].split('?')[0].split('#')[0];
    a.setAttribute('href', parte + '.html');
  });
})();
