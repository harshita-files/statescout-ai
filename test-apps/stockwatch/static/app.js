(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var last = {};

  // theme
  var tt = $('#theme-toggle');
  if (tt) tt.addEventListener('click', function () {
    var cur = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', cur);
    try { localStorage.setItem('sw-theme', cur); } catch (e) {}
  });

  function sgn(n) { return (n > 0 ? '+' : '') + n.toFixed(2); }
  function sparkPath(vals, w, h) {
    var mn = Math.min.apply(null, vals), mx = Math.max.apply(null, vals), rg = (mx - mn) || 1;
    return vals.map(function (v, i) {
      return (i ? 'L' : 'M') + (i * w / (vals.length - 1)).toFixed(1) + ' ' + (h - 2 - (v - mn) / rg * (h - 4)).toFixed(1);
    }).join(' ');
  }

  function apply(data) {
    var Q = data.quotes;
    $$('[data-symbol][data-field]').forEach(function (el) {
      var q = Q[el.getAttribute('data-symbol')];
      if (!q) return;
      var f = el.getAttribute('data-field'), txt, dir = q.change >= 0 ? 'up' : 'down';
      if (f === 'price') txt = q.price.toFixed(2);
      else if (f === 'ticket') txt = (q.price * 1.02).toFixed(2);
      else if (f === 'change') { txt = sgn(q.change); el.className = 'num ' + dir; }
      else if (f === 'pct') { txt = (q.pct > 0 ? '+' : '') + q.pct.toFixed(2) + '%'; el.className = 'num ' + dir; }
      else if (f === 'volume') txt = q.volume.toLocaleString();
      else if (f === 'value') txt = (q.price * parseFloat(el.getAttribute('data-qty'))).toFixed(2);
      else return;
      if (el.textContent !== txt) {
        if (f === 'price' || f === 'ticket') {
          var key = el.getAttribute('data-symbol') + f, prev = last[key];
          if (prev !== undefined) {
            el.classList.remove('flash-up', 'flash-down'); void el.offsetWidth;
            el.classList.add(q.price >= prev ? 'flash-up' : 'flash-down');
          }
          last[key] = q.price;
        }
        el.textContent = txt;
      }
    });
    $$('svg.spark[data-symbol]').forEach(function (s) {
      var q = Q[s.getAttribute('data-symbol')];
      if (!q) return;
      s.setAttribute('class', 'spark ' + (q.change >= 0 ? 'up' : 'down'));
      s.firstElementChild.setAttribute('d', sparkPath(q.spark, 110, 30));
    });
    var pf = $('[data-field=pftotal]');
    if (pf) {
      var sum = 0; $$('td[data-field=value]').forEach(function (e) { sum += parseFloat(e.textContent); });
      pf.textContent = (sum + parseFloat(pf.getAttribute('data-adj'))).toFixed(2);
    }
    var lu = $('#last-updated'); if (lu) lu.textContent = data.updated_at;
  }

  function startLive() {
    var poll = function () { fetch('/api/quotes').then(function (r) { return r.json(); }).then(apply).catch(function () {}); };
    if (window.EventSource) {
      var es = new EventSource('/api/stream');
      es.onmessage = function (e) { try { apply(JSON.parse(e.data)); } catch (x) {} };
      es.onerror = function () { es.close(); setInterval(poll, 3000); };
    } else { setInterval(poll, 3000); }
  }
  startLive();

  // watchlist stars
  $$('.star').forEach(function (b) {
    b.addEventListener('click', function () {
      fetch('/api/watchlist', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: b.getAttribute('data-symbol') }) })
        .then(function (r) { return r.json(); })
        .then(function (d) { b.setAttribute('aria-pressed', d.watching ? 'true' : 'false');
          if (document.body.getAttribute('data-page') === 'watchlist' && !d.watching) location.reload(); });
    });
  });

  // client side live filter
  var qi = $('#q');
  if (qi) qi.addEventListener('input', function () {
    var v = qi.value.toLowerCase();
    $$('tbody tr[data-symbol]').forEach(function (tr) { tr.hidden = v && tr.textContent.toLowerCase().indexOf(v) < 0; });
  });

  // promo modal (random)
  function showPromo(p) {
    var bg = document.createElement('div'); bg.className = 'modal-bg'; bg.id = 'promo';
    bg.innerHTML = '<div class="modal" role="dialog" aria-modal="true" aria-labelledby="promo-t"><h2 id="promo-t"></h2><p></p>' +
      '<div class="row"><a class="btn primary" id="promo-cta">Claim offer</a><button class="btn" id="promo-x" type="button">Close</button></div></div>';
    $('h2', bg).textContent = p.title; $('p', bg).textContent = p.body; $('#promo-cta', bg).href = p.href;
    document.body.appendChild(bg);
    $('#promo-x', bg).focus();
    $('#promo-x', bg).addEventListener('click', function () { bg.remove(); });
  }
  setTimeout(function () {
    fetch('/api/promo').then(function (r) { return r.json(); }).then(function (p) { if (p && p.title) showPromo(p); }).catch(function () {});
  }, 1200);

  // trade form
  var tf = $('#order-form');
  if (tf) {
    var sel = $('#symbol', tf);
    sel.addEventListener('change', function () { location.href = '/trade?symbol=' + sel.value; });
    tf.addEventListener('submit', function (e) {
      e.preventDefault();
      var body = { symbol: sel.value, side: (tf.elements.side.value || 'buy'), qty: $('#qty').value, type: $('#otype').value };
      fetch('/api/order', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var n = $('#order-result'); n.hidden = false;
          n.className = 'notice ' + (d.ok ? 'ok' : 'err'); n.textContent = d.message;
        });
    });
  }

  // stock page
  var sp = $('#stock-page');
  if (sp) {
    var sym = sp.getAttribute('data-symbol');
    var show = function () {
      var h = (location.hash || '#overview').slice(1);
      $$('.tab').forEach(function (t) { t.setAttribute('aria-selected', t.getAttribute('data-tab') === h ? 'true' : 'false'); });
      $$('[data-panel]').forEach(function (p) { p.hidden = p.getAttribute('data-panel') !== h; });
      if (h === 'chart') drawChart();
    };
    window.addEventListener('hashchange', show);
    var mode = 'candles';
    $$('.seg button').forEach(function (b) {
      b.addEventListener('click', function () {
        mode = b.getAttribute('data-mode');
        $$('.seg button').forEach(function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
        drawChart();
      });
    });
    var drawChart = function () {
      fetch('/api/candles?symbol=' + sym + '&n=48').then(function (r) { return r.json(); }).then(function (d) {
        var C = d.candles, W = 720, H = 300, pad = 28;
        var lo = Math.min.apply(null, C.map(function (c) { return c.l; })), hi = Math.max.apply(null, C.map(function (c) { return c.h; }));
        var y = function (v) { return pad + (hi - v) / ((hi - lo) || 1) * (H - 2 * pad); };
        var step = (W - 2 * pad) / C.length, s = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + sym + ' price chart">';
        for (var i = 0; i <= 4; i++) {
          var v = lo + (hi - lo) * i / 4;
          s += '<line x1="' + pad + '" x2="' + (W - pad) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="currentColor" opacity=".12"/><text x="2" y="' + (y(v) + 4) + '" font-size="10" fill="currentColor" opacity=".6">' + v.toFixed(0) + '</text>';
        }
        if (mode === 'line') {
          s += '<path fill="none" stroke="var(--brand)" stroke-width="2" d="' + C.map(function (c, i) { return (i ? 'L' : 'M') + (pad + i * step + step / 2) + ' ' + y(c.c); }).join(' ') + '"/>';
        } else {
          C.forEach(function (c, i) {
            var x = pad + i * step + step / 2, col = c.c >= c.o ? 'var(--up)' : 'var(--down)';
            s += '<line x1="' + x + '" x2="' + x + '" y1="' + y(c.h) + '" y2="' + y(c.l) + '" stroke="' + col + '"/><rect x="' + (x - step * .34) + '" y="' + Math.min(y(c.o), y(c.c)) + '" width="' + step * .68 + '" height="' + Math.max(1.5, Math.abs(y(c.o) - y(c.c))) + '" fill="' + col + '"/>';
          });
        }
        $('#chart').innerHTML = s + '</svg>';
      });
    };
    // flaky quote endpoint; rendering is deliberately unguarded
    var loadQuote = function () {
      fetch('/api/quote?symbol=' + sym).then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      }).then(function (q) {
        $('#q-bid').textContent = '$' + Number(q.bid).toFixed(2);
        $('#q-ask').textContent = '$' + Number(q.ask).toFixed(2);
        $('#q-vol').textContent = q.volume + ' shares';
        $('#q-err').hidden = true;
      }).catch(function () { $('#q-err').hidden = false; });
    };
    loadQuote(); setInterval(loadQuote, 4000);
    var rt = $('#q-retry'); if (rt) rt.addEventListener('click', loadQuote);
    show();
  }
})();
