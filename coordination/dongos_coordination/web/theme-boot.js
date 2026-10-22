/* Apply the saved or system colour scheme before the first paint. */
(function () {
  var dark = false;
  try {
    var saved = localStorage.getItem('coordination-theme');
    dark = saved === 'dark' || saved === 'light'
      ? saved === 'dark'
      : !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
  } catch (error) {
    dark = !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
  }
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
})();
