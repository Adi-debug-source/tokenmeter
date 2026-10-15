/* Tokenmeter dashboard behaviour.
   Convert currency in place, draw the time chart, reveal on scroll, and with
   several harnesses show one of them on its own. No framework, no build step,
   nothing fetched at open time, and no figure computed here: every total was
   worked out by tokenmeter.py and only added up or scaled for drawing. */
const D = __PAYLOAD__;
const SLOW = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const clamp = (lo, hi, v) => Math.max(lo, Math.min(hi, v));
const callsText = n => n.toLocaleString('en-US') + (n === 1 ? ' call' : ' calls');
/* Text bound for markup. A provider's name comes from the logs or an import,
   and one holding markup ran when the tooltip showed it, so every string goes
   through here before it meets innerHTML; only numbers and the engine's fixed
   colours go in as they are. */
const esc = v => String(v).replace(/[&<>"']/g,
  c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[c]);

/* ---- money. Same rule as money() in tokenmeter.py. Three copies of this
   exist, one per face, and they must agree or one figure reads two ways.
   A negative amount takes its minus before the symbol: -$0.10, not $-0.10.
   Separators are en-US, not the browser's own, so 1,234.50 reads the same
   here as in the terminal on a Mac set to any language. ---- */
function fmt(usd, cur) {
  const x = usd * (D.rates[cur] || 1), s = D.symbols[cur] || '$';
  if (x === 0) return s + '0.00';
  const sign = x < 0 ? '-' : '', a = Math.abs(x);
  if (a < 0.00005) return sign + '<' + s + '0.0001';
  if (a < 0.01) return sign + s + a.toFixed(4);
  return sign + s + a.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}
let CUR = D.current;

function valueOf(el) {
  if (el.dataset.usdBig !== undefined) {
    // Rounded first, then subtracted, so the column still adds up after
    // conversion and not only in the currency it was rendered in.
    const r = D.rates[CUR] || 1;
    return (Math.round(parseFloat(el.dataset.usdBig) * r * 100) -
            Math.round(parseFloat(el.dataset.usdSmall) * r * 100)) / 100 / r;
  }
  return parseFloat(el.dataset.usd);
}

/* Tween every figure to its new value rather than snapping. A switch you can
   watch happen is a switch you believe. */
function tweenAll(dur) {
  const els = [].slice.call(document.querySelectorAll('.m'));
  const from = els.map(el => parseFloat(el.dataset.shown || '0'));
  const to = els.map(valueOf);
  if (SLOW || !dur) {
    els.forEach((el, i) => { el.textContent = fmt(to[i], CUR); el.dataset.shown = to[i]; });
    return;
  }
  const t0 = performance.now();
  (function step(now) {
    const p = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - p, 3);
    els.forEach(function (el, i) {
      const v = from[i] + (to[i] - from[i]) * e;
      el.textContent = fmt(v, CUR);
      if (p === 1) el.dataset.shown = to[i];
    });
    if (p < 1) requestAnimationFrame(step);
  })(t0);
}

/* ---- pages. One per harness when there are several, all rendered up front;
   the Harness menu beside the currencies chooses which one shows. All
   harnesses together is the default. ---- */
let ACTIVE = D.first;
const HIDDEN = {};   // series switched off in the chart's legend
const view = key => document.querySelector('.view[data-view="' + key + '"]');
document.querySelectorAll('.hsel').forEach(s => { s.value = ACTIVE; });

function show(key) {
  if (!view(key)) return;
  ACTIVE = key;
  document.querySelectorAll('.view').forEach(v => { v.hidden = v.dataset.view !== key; });
  document.querySelectorAll('.hsel').forEach(s => { s.value = key; });
  drawChart();
}
document.querySelectorAll('.hsel').forEach(s => s.addEventListener('change', () => show(s.value)));

function paint(cur, tween) {
  CUR = cur;
  tweenAll(tween ? 620 : 0);
  document.querySelectorAll('.pill').forEach(b => b.classList.toggle('on', b.dataset.cur === cur));
  document.querySelectorAll('.rate-note').forEach(function (note) {
    note.textContent = cur === 'USD'
      ? 'Billed currency. No conversion applied.'
      : (D.rates[cur] || 1).toFixed(4) + ' to the dollar · ' + D.rateWhen;
  });
  try { localStorage.setItem('cur', cur); } catch (e) {}
  drawChart();
}
document.querySelectorAll('.pill').forEach(function (b) {
  b.addEventListener('click', () => paint(b.dataset.cur, true));
});

/* ---- the time chart ---- */
let MODE = 'cost';

function drawChart() {
  const root = view(ACTIVE);
  const host = root && root.querySelector('.chart');
  const svg = host && host.querySelector('svg');
  const V = D.views[ACTIVE] || {days: []};
  const days = V.days;
  /* With several harnesses each day's bar is split between them. A series
     switched off in the legend leaves the bars, the scale and the running
     total, so what remains can be read on its own. */
  const stacked = !!(V.series && V.series.length);
  const series = stacked ? V.series.filter(s => !HIDDEN[s.name]) : [];
  if (!svg || !days.length) return;
  const W = Math.max(320, host.clientWidth), H = 268;
  /* The viewBox must match the pixel box we draw in. It used to be a fixed
     900 while the drawing used clientWidth, so everything rendered scaled by
     clientWidth/900 and the crosshair landed to the right of its own bar. */
  svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
  svg.setAttribute('height', H);

  const padL = 54, padR = 16, padT = 16, padB = 28;
  const iw = W - padL - padR, ih = H - padT - padB;
  const rate = D.rates[CUR] || 1, sym = D.symbols[CUR] || '$', pageId = esc(ACTIVE);

  const part = (d, s) => MODE === 'cost' ? (d.by[s.name] || 0) * rate : (d.byTok[s.name] || 0);
  const val = d => stacked ? series.reduce((a, s) => a + part(d, s), 0)
                           : (MODE === 'cost' ? d.total * rate : d.tokens);
  const peak = Math.max.apply(null, days.map(val)) || 1;
  let run = 0;
  const cum = days.map(d => (run += val(d)));
  const cumPeak = run || 1;

  const bw = iw / days.length;
  const x = i => padL + i * bw;
  const y = v => padT + ih - (v / peak) * ih;
  const yc = v => padT + ih - (v / cumPeak) * ih;
  host._geom = {padL, padT, ih, bw, x, yc, cum, rate, days, series, stacked};

  /* Small figures get the decimals they need: a page of pennies otherwise
     read $0.0 on every line of the axis. */
  const dp = peak >= 1 ? -1 : peak >= 0.1 ? 2 : 3;
  const shortNum = v => MODE === 'cost'
    ? (v >= 1000 ? sym + Math.round(v / 1000) + 'k'
       : sym + (dp < 0 ? v.toFixed(v < 10 ? 1 : 0) : v.toFixed(dp)))
    : (v >= 1e9 ? (v / 1e9).toFixed(1) + 'B' : v >= 1e6 ? Math.round(v / 1e6) + 'M'
       : v >= 1e3 ? Math.round(v / 1e3) + 'k' : Math.round(v));

  let g = '';
  for (let i = 0; i <= 4; i++) {
    const yy = padT + ih - (i / 4) * ih;
    g += '<line class="gridline" x1="' + padL + '" y1="' + yy + '" x2="' + (W - padR) + '" y2="' + yy + '"/>' +
         '<text class="axlab" x="' + (padL - 9) + '" y="' + (yy + 3.5) + '" text-anchor="end">' +
         esc(shortNum(peak * i / 4)) + '</text>';
  }

  const grow = (i, top, h) => SLOW ? '' :
    '<animate attributeName="height" values="0;' + h.toFixed(2) + '" dur="0.75s" begin="' +
    Math.min(500, i * 8) + 'ms" fill="freeze" calcMode="spline" keySplines="0.22 0.68 0.16 1" keyTimes="0;1"/>' +
    '<animate attributeName="y" values="' + (padT + ih) + ';' + top.toFixed(2) + '" dur="0.75s" begin="' +
    Math.min(500, i * 8) + 'ms" fill="freeze" calcMode="spline" keySplines="0.22 0.68 0.16 1" keyTimes="0;1"/>';

  let bars = '';
  days.forEach(function (d, i) {
    const v = val(d), h = Math.max(v > 0 ? 1.5 : 0, (v / peak) * ih);
    const bx = x(i) + bw * 0.17, bwid = Math.max(1, bw * 0.66);
    const rx = Math.min(2.5, bw * 0.3).toFixed(2);
    if (!stacked) {
      bars += '<rect class="dbar" data-i="' + i + '" style="fill:url(#bargrad-' + pageId + ')" x="' +
              bx.toFixed(2) + '" y="' + (padT + ih - h).toFixed(2) +
              '" width="' + bwid.toFixed(2) + '" height="' + h.toFixed(2) + '" rx="' + rx + '">' +
              grow(i, padT + ih - h, h) + '</rect>';
      return;
    }
    /* Segments stacked from the baseline in the legend's order, a pixel of
       page between neighbours so two similar colours never merge. */
    let base = padT + ih;
    const shown = series.filter(s => part(d, s) > 0);
    shown.forEach(function (s, j) {
      const sh = v > 0 ? h * part(d, s) / v : 0;
      const gap = j < shown.length - 1 && sh > 2 ? 1 : 0;
      const top = base - sh;
      bars += '<rect class="dbar" data-i="' + i + '" style="fill:' + s.color + '" x="' + bx.toFixed(2) +
              '" y="' + top.toFixed(2) + '" width="' + bwid.toFixed(2) + '" height="' + (sh - gap).toFixed(2) +
              '" rx="' + (j === shown.length - 1 ? rx : 0) + '">' + grow(i, top, sh - gap) + '</rect>';
      base = top;
    });
  });

  let line = '';
  days.forEach(function (d, i) {
    line += (i ? 'L' : 'M') + (x(i) + bw / 2).toFixed(1) + ' ' + yc(cum[i]).toFixed(1) + ' ';
  });
  const area = line + 'L' + (x(days.length - 1) + bw / 2).toFixed(1) + ' ' + (padT + ih) +
               ' L' + (x(0) + bw / 2).toFixed(1) + ' ' + (padT + ih) + ' Z';

  let ticks = '';
  const every = Math.max(1, Math.round(days.length / 8));
  days.forEach(function (d, i) {
    if (i % every && i !== days.length - 1) return;
    ticks += '<text class="axlab" x="' + (x(i) + bw / 2).toFixed(1) + '" y="' + (H - 7) +
             '" text-anchor="middle">' + esc(d.short) + '</text>';
  });

  /* Split bars already use the harness colours, so the running total drops
     to a neutral line rather than wearing one of them. */
  const lineColour = stacked ? '#c3cad4' : '#5b9dd9';
  svg.innerHTML =
    '<defs>' +
    /* Ids carry the page's name: a gradient defined inside a hidden page
       can fail to paint the page that is showing. */
    '<linearGradient id="bargrad-' + pageId + '" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0%" stop-color="#e8916f"/><stop offset="100%" stop-color="#c9663f"/></linearGradient>' +
    '<linearGradient id="cumgrad-' + pageId + '" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0%" stop-color="' + lineColour + '" stop-opacity="' + (stacked ? '.12' : '.22') + '"/>' +
      '<stop offset="100%" stop-color="' + lineColour + '" stop-opacity="0"/></linearGradient></defs>' +
    g + '<path class="cumfill" style="fill:url(#cumgrad-' + pageId + ')" d="' + area + '"/>' + bars +
    '<path class="cum' + (stacked ? ' neutral' : '') + '" d="' + line + '"' +
      (SLOW ? '' : ' stroke-dasharray="5000" stroke-dashoffset="5000">' +
        '<animate attributeName="stroke-dashoffset" values="5000;0" dur="1.7s" begin="0.15s" fill="freeze"/></path>') +
      (SLOW ? '/>' : '') +
    '<line class="cross" y1="' + padT + '" y2="' + (padT + ih) + '"/>' +
    '<circle class="knob' + (stacked ? ' neutral' : '') + '" r="4.5"/>' + ticks +
    '<rect class="hit" x="' + padL + '" y="' + padT + '" width="' + iw + '" height="' + ih + '"/>';

  svg.querySelector('.hit').addEventListener('mousemove', e => onMove(e, host));
  svg.querySelector('.hit').addEventListener('mouseleave', () => onLeave(host));
}

function onMove(e, host) {
  const box = host.getBoundingClientRect();
  const {padL, bw, x, yc, cum, rate, days, series, stacked} = host._geom;
  const i = clamp(0, days.length - 1, Math.floor((e.clientX - box.left - padL) / bw));
  const d = days[i], cx = x(i) + bw / 2;

  const cross = host.querySelector('.cross'), knob = host.querySelector('.knob');
  cross.setAttribute('x1', cx); cross.setAttribute('x2', cx); cross.style.opacity = 1;
  knob.setAttribute('cx', cx); knob.setAttribute('cy', yc(cum[i])); knob.style.opacity = 1;
  host.querySelectorAll('.dbar').forEach(b => b.classList.toggle('dull', +b.dataset.i !== i));

  const running = MODE === 'cost' ? fmt(cum[i] / rate, CUR)
    : (cum[i] >= 1e9 ? (cum[i] / 1e9).toFixed(2) + 'B' : Math.round(cum[i] / 1e6) + 'M') + ' tokens';
  const tip = host.querySelector('.tip');
  if (stacked) {
    const usd = series.reduce((a, s) => a + (d.by[s.name] || 0), 0);
    const calls = series.reduce((a, s) => a + (d.byCalls[s.name] || 0), 0);
    tip.innerHTML = '<i>' + esc(d.full) + '</i><b>' + esc(fmt(usd, CUR)) + '</b>' +
      series.filter(s => d.by[s.name]).map(s => '<i><span class="sw" style="background:' + s.color +
        '"></span>' + esc(s.label + ' ' + fmt(d.by[s.name], CUR)) + '</i>').join('') +
      '<i>' + esc(callsText(calls) + ' · running ' + running) + '</i>';
  } else {
    tip.innerHTML = '<i>' + esc(d.full) + '</i><b>' + esc(fmt(d.total, CUR)) + '</b><i>' +
      esc(callsText(d.calls) + ' · ' + d.tokShort + ' tokens') + '</i><i>' + esc('running ' + running) + '</i>';
  }
  tip.classList.add('on');

  /* Sit beside the bar, never on top of it. Flip to the other side near the
     right edge. Overlapping the thing you are describing hides the answer. */
  const gap = 18, tw = tip.offsetWidth, th = tip.offsetHeight;
  let left = cx + gap;
  if (left + tw > box.width - 2) left = cx - gap - tw;
  tip.style.left = clamp(0, Math.max(0, box.width - tw), left) + 'px';
  tip.style.top = clamp(0, Math.max(0, box.height - th), e.clientY - box.top - th / 2) + 'px';
}

function onLeave(host) {
  host.querySelector('.tip').classList.remove('on');
  host.querySelector('.cross').style.opacity = 0;
  host.querySelector('.knob').style.opacity = 0;
  host.querySelectorAll('.dbar').forEach(b => b.classList.remove('dull'));
}

document.querySelectorAll('.tg').forEach(function (b) {
  b.addEventListener('click', function () {
    MODE = b.dataset.mode;
    document.querySelectorAll('.tg').forEach(x => x.classList.toggle('on', x.dataset.mode === MODE));
    drawChart();
  });
});

/* The chart's legend switches a harness in and out. Switching off the last
   one brings them all back rather than leaving an empty chart. */
document.querySelectorAll('.sl').forEach(function (b) {
  b.addEventListener('click', function () {
    const name = b.dataset.series, V = D.views[ACTIVE];
    HIDDEN[name] = !HIDDEN[name];
    if (V.series && V.series.every(s => HIDDEN[s.name])) V.series.forEach(s => { delete HIDDEN[s.name]; });
    document.querySelectorAll('.sl').forEach(x => x.classList.toggle('off', !!HIDDEN[x.dataset.series]));
    drawChart();
  });
});

/* legend hover dims the rest, so one component can be read alone */
document.querySelectorAll('.legend').forEach(function (legend) {
  legend.addEventListener('mouseenter', () => legend.classList.add('muted'));
  legend.addEventListener('mouseleave', () => legend.classList.remove('muted'));
});

/* ---- reveal on scroll, with the table rows stepping in ---- */
const io = new IntersectionObserver(function (entries) {
  entries.forEach(function (en) {
    if (!en.isIntersecting) return;
    en.target.classList.add('reveal');
    en.target.querySelectorAll('tbody tr').forEach(function (tr, i) {
      tr.style.transitionDelay = Math.min(360, i * 42) + 'ms';
    });
    io.unobserve(en.target);
  });
}, {threshold: 0.1, rootMargin: '0px 0px -40px 0px'});
document.querySelectorAll('.fade,.reveal-on').forEach(el => io.observe(el));

let rt;
window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(drawChart, 130); });

let stored = null;
try { stored = localStorage.getItem('cur'); } catch (e) {}
paint(stored && D.rates[stored] ? stored : D.current, false);

/* headline settles out of a blur as it counts */
const hero = view(ACTIVE) && view(ACTIVE).querySelector('.headline');
if (hero && !SLOW) {
  hero.classList.add('settling');
  const target = parseFloat(hero.dataset.usd), t0 = performance.now(), dur = 1250;
  (function step(now) {
    const p = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - p, 4);
    hero.textContent = fmt(target * e, CUR);
    if (p < 1) requestAnimationFrame(step);
    else { hero.dataset.shown = target; hero.classList.remove('settling'); }
  })(t0);
}
