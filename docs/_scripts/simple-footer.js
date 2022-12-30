const i = function() {
  return {
    load: !1,
    content: ""
  };
}, c = function() {
  return {
    main: i(),
    sidebar: i()
  };
};
function m(f, y) {
  let l = function(o, e) {
    const n = document.createElement("small");
    return n.innerHTML = o, n.id = e, n.className = `docsify-footer-${e}`, n;
  }, s = function(o, e) {
    return l(o, `main-${e}`);
  }, d = function(o) {
    let e = $docsify.footer.main, n = e.content;
    if (typeof n == "string")
      o.innerHTML = n;
    else if (typeof e == "object")
      for (let t in e)
        t !== "load" && o.appendChild(s(e[t], t));
    return o;
  }, r = function(o) {
    let e = document.createElement("div");
    return e.className = "docsify-footer-container", e.id = "docsify-footer-main", o.main.load ? o.main.content.length > 0 && fetch(o.main.content).then((n) => n.text()).then((n) => {
      e.innerHTML = n;
    }) : e = d(e), e;
  }, a = function() {
    typeof $docsify.footer > "u" ? $docsify.footer = c() : typeof $docsify.footer == "string" && ($docsify.footer = {
      main: {
        load: endsWith($docsify.footer, ".md", ".html", ".txt"),
        content: $docsify.footer
      }
    }), $docsify.footer = Object.assign(c(), $docsify.footer);
    let o = $docsify.footer, e = r(o), n = document.createElement("footer");
    n.appendChild(e), document.querySelector(".content").appendChild(n);
  };
  f.mounted(a);
}
function u() {
  window.$docsify = window.$docsify || {}, $docsify.plugins = $docsify.plugins || [], console.log("install"), $docsify.plugins = [].concat(m, $docsify.plugins || []);
}
u();
