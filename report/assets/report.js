// Draws every chart and table on the report page from the JSON files in data/.
// Plain SVG, no dependencies. Each chart redraws when its container changes width.
(() => {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const DATASETS = ['routers', 'traffic', 'harness', 'runs', 'windows', 'pilot', 'timeline', 'scope', 'slices', 'study', 'native'];
  const ROUTERS = ['rr', 'kv', 'kvp16', 'aff'];
  const ORDER = ['rr', 'kv', 'kvp4', 'kvp16', 'aff'];
  const LABEL = {
    rr: 'Round-robin', kv: 'KV router, defaults', kvp4: 'KV router, prefill_load_scale 4',
    kvp16: 'KV router, prefill_load_scale 16', aff: 'KV router with session affinity',
  };
  const SHORT = { rr: 'Round-robin', kv: 'KV defaults', kvp4: 'KV scale 4', kvp16: 'KV scale 16', aff: 'Affinity' };
  const TINY = { rr: 'RR', kv: 'KV', kvp16: 'KV 16', aff: 'Aff.' };
  const COLOR = { rr: 'var(--r-rr)', kv: 'var(--r-kv)', kvp4: 'var(--r-kvp16)', kvp16: 'var(--r-kvp16)', aff: 'var(--r-aff)' };
  const INK = 'var(--ink)', NEUTRAL = 'var(--neutral)', PAPER = 'var(--paper)';
  const SLA_SHARE = 99, SLA_TTFT_MS = 2000;

  // Number formats. One rule per quantity, used by every table, chart and tooltip.
  const nf = (d) => new Intl.NumberFormat('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  const F0 = nf(0), F1 = nf(1), F2 = nf(2);
  const int = (v) => F0.format(v);
  const pct = (v) => `${F1.format(v)}%`;
  const pct0 = (v) => `${F0.format(v)}%`;
  // A share just under the 99% threshold keeps a second decimal, so it never prints as 99.0%.
  const share = (v) => (v < 99 && v >= 98.95 ? `${F2.format(v)}%` : pct(v));
  const bn = (v) => `${F1.format(v)}B`;
  const bn2 = (v) => F2.format(v);
  const mInt = (v) => `${F0.format(v)}M`;
  const m1 = (v) => `${F1.format(v)}M`;
  const ratio = (v) => `${F1.format(v)}x`;
  const min1 = (v) => `${F1.format(v)} min`;
  const ms = (v) => (v < 2000 ? `${F0.format(v)} ms` : v < 100000 ? `${F1.format(v / 1000)} s` : `${F0.format(v / 1000)} s`);
  const signed = (v) => `${v > 0 ? '+' : ''}${F1.format(v)}%`;
  const utc = (unix) => new Date(unix * 1000).toISOString().slice(0, 16).replace('T', ' ');

  const el = (tag, attrs, parent) => {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  };
  const text = (parent, x, y, str, attrs) => {
    const t = el('text', Object.assign({ x, y }, attrs || {}), parent);
    t.textContent = str;
    return t;
  };
  const html = (tag, cls, str) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (str != null) n.textContent = str;
    return n;
  };
  const ticks = (max, n) => {
    const raw = max / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((s) => s * mag).find((s) => s >= raw);
    const out = [];
    for (let v = 0; v < max + step * 0.999; v += step) out.push(+v.toFixed(6));
    return out;
  };
  const lin = (d0, d1, r0, r1) => (v) => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);
  const logScale = (d0, d1, r0, r1) => (v) => r0 + ((Math.log10(v) - Math.log10(d0)) / (Math.log10(d1) - Math.log10(d0))) * (r1 - r0);
  const widthOf = (host) => Math.max(240, Math.floor(host.clientWidth));
  const start = (host, W, H, label) => {
    host.replaceChildren();
    const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', 'aria-roledescription': 'chart', 'aria-label': label });
    host.appendChild(svg);
    return svg;
  };
  const resize = (svg, W, H) => { svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('height', H); };
  // Bar with a rounded data end and a square baseline end.
  const barPath = (x, y, w, h, r) => {
    r = Math.min(r, w, h / 2);
    return `M${x} ${y}h${w - r}a${r} ${r} 0 0 1 ${r} ${r}v${h - 2 * r}a${r} ${r} 0 0 1 -${r} ${r}h-${w - r}z`;
  };
  const colPath = (x, base, w, h, r) => {
    r = Math.min(r, w / 2, h);
    return `M${x} ${base}v-${h - r}a${r} ${r} 0 0 1 ${r} -${r}h${w - 2 * r}a${r} ${r} 0 0 1 ${r} ${r}v${h - r}z`;
  };
  // Keep a centered label inside [lo, hi] by switching its anchor at the edges.
  const clamp = (t, lo, hi) => {
    const x = +t.getAttribute('x'), w = t.getComputedTextLength();
    if (x - w / 2 < lo) { t.setAttribute('text-anchor', 'start'); t.setAttribute('x', lo); }
    else if (x + w / 2 > hi) { t.setAttribute('text-anchor', 'end'); t.setAttribute('x', hi); }
    return t;
  };
  const diamond = (x, y, r) => `M${x} ${y - r}l${r} ${r}l-${r} ${r}l-${r} -${r}z`;
  // Mark shapes shared by the dot charts. Filled marks carry a ring in the surface color.
  const mark = (g, shape, x, y, color, opts = {}) => {
    const style = { dot: `fill:${color};stroke:${PAPER};stroke-width:2`, ring: `fill:${PAPER};stroke:${color};stroke-width:2.25`, dia: `fill:${color};stroke:${PAPER};stroke-width:1.5` }[shape];
    const n = shape === 'dia' ? el('path', { d: diamond(x, y, 6), style }, g) : el('circle', { cx: x, cy: y, r: shape === 'ring' ? 4.4 : 5, style }, g);
    if (opts.opacity) n.setAttribute('opacity', opts.opacity);
    n.setAttribute('class', 'ap');
    return n;
  };

  // One tooltip for the page.
  const tipEl = html('div', 'tip');
  tipEl.hidden = true;
  const showTip = (cx, cy, title, lines) => {
    tipEl.replaceChildren(html('div', 't', title));
    for (const [key, value, color] of lines) {
      const row = document.createElement('div');
      if (color) { const k = html('span', 'k'); k.style.background = color; row.appendChild(k); }
      row.appendChild(html('b', '', value));
      row.appendChild(document.createTextNode(` ${key}`));
      tipEl.appendChild(row);
    }
    tipEl.hidden = false;
    const w = tipEl.offsetWidth, h = tipEl.offsetHeight;
    tipEl.style.left = `${Math.max(8, Math.min(window.innerWidth - w - 8, cx + 14))}px`;
    tipEl.style.top = `${cy - h - 14 < 8 ? cy + 18 : cy - h - 14}px`;
  };
  const hideTip = () => { tipEl.hidden = true; };

  // Hover, touch and keyboard for one chart. pts: {x, y} or {box: {x, y, w, h}}, plus title and lines.
  // The pointer selects the box it is in, or the nearest point. Arrow keys step through the points.
  function interact(svg, pts, opts = {}) {
    if (!pts.length) return;
    const W = svg.viewBox.baseVal.width;
    const halo = el('circle', { r: 9, class: 'halo', visibility: 'hidden' }, svg);
    const frame = el('rect', { rx: 3, class: 'halo', visibility: 'hidden' }, svg);
    const cross = opts.cross ? el('line', { y1: opts.cross[0], y2: opts.cross[1], class: 'base', visibility: 'hidden' }, svg) : null;
    if (cross) svg.insertBefore(cross, svg.firstChild);
    let cur = -1;
    const clear = () => {
      cur = -1; hideTip();
      halo.setAttribute('visibility', 'hidden'); frame.setAttribute('visibility', 'hidden');
      if (cross) cross.setAttribute('visibility', 'hidden');
    };
    const select = (i, cx, cy) => {
      cur = i;
      const p = pts[i];
      if (cross) { cross.setAttribute('x1', p.x); cross.setAttribute('x2', p.x); cross.setAttribute('visibility', 'visible'); }
      if (p.box) {
        const b = p.box;
        for (const [k, v] of [['x', b.x], ['y', b.y], ['width', b.w], ['height', b.h]]) frame.setAttribute(k, v);
        frame.setAttribute('visibility', opts.quiet ? 'hidden' : 'visible'); halo.setAttribute('visibility', 'hidden');
      } else if (!cross) {
        halo.setAttribute('cx', p.x); halo.setAttribute('cy', p.y);
        halo.setAttribute('visibility', 'visible'); frame.setAttribute('visibility', 'hidden');
      }
      if (cx == null) {
        const r = svg.getBoundingClientRect(), k = r.width / W;
        cx = r.left + (p.box ? p.box.x + p.box.w / 2 : p.x) * k;
        cy = r.top + (p.box ? p.box.y : p.y) * k;
      }
      showTip(cx, cy, p.title, p.lines);
    };
    const onPointer = (e) => {
      const r = svg.getBoundingClientRect(), k = W / r.width;
      const mx = (e.clientX - r.left) * k, my = (e.clientY - r.top) * k;
      let best = -1, bd = opts.cross ? Infinity : (opts.radius || 30) ** 2;
      for (let i = 0; i < pts.length; i++) {
        const p = pts[i];
        let d;
        if (p.box) d = mx >= p.box.x && mx <= p.box.x + p.box.w && my >= p.box.y && my <= p.box.y + p.box.h ? 0 : Infinity;
        else if (opts.cross) d = (p.x - mx) ** 2;
        else d = (p.x - mx) ** 2 + (p.y - my) ** 2;
        if (d < bd) { bd = d; best = i; }
      }
      if (best < 0) clear(); else select(best, e.clientX, e.clientY);
    };
    svg.addEventListener('pointermove', onPointer);
    svg.addEventListener('pointerdown', onPointer);
    svg.addEventListener('pointerleave', clear);
    svg.setAttribute('tabindex', '0');
    svg.addEventListener('focus', () => { if (svg.matches(':focus-visible') && cur < 0) select(0); });
    svg.addEventListener('blur', clear);
    svg.addEventListener('keydown', (e) => {
      const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
      if (step) { e.preventDefault(); select((Math.max(cur, 0) + (cur < 0 ? 0 : step) + pts.length) % pts.length); }
      else if (e.key === 'Home') { e.preventDefault(); select(0); }
      else if (e.key === 'End') { e.preventDefault(); select(pts.length - 1); }
      else if (e.key === 'Escape') clear();
    });
  }

  const routerRows = (D, scope) => ROUTERS.map((r) => D.routers.find((x) => x.scope === scope && x.router === r));
  const family = (traffic) => traffic.split(' ')[0];

  // Cover figure. Each router's prefill as blocks the size of the session-affinity total.
  function hero(host, D) {
    const rows = routerRows(D, 'all'), unit = rows[3].prefill_tokens_b;
    const W = widthOf(host), rowH = 62, H = rows.length * rowH - 12;
    const svg = start(host, W, H, `Prefill tokens across all ${rows[0].units} runs: ${rows.map((r) => `${LABEL[r.router]} ${bn(r.prefill_tokens_b)}, ${ratio(r.prefill_vs_affinity)} session affinity`).join('; ')}.`);
    const groups = rows.map((r, i) => {
      const g = el('g', { transform: `translate(0,${i * rowH})` }, svg);
      text(g, 0, 13, LABEL[r.router], { class: 'lab' });
      const val = text(g, 0, 40, '', {});
      const a = el('tspan', { class: 'strong', 'font-size': 14 }, val); a.textContent = bn(r.prefill_tokens_b);
      const b = el('tspan', { dx: 9 }, val); b.textContent = ratio(r.prefill_vs_affinity);
      return { g, val, r };
    });
    const labelW = Math.max(...groups.map((x) => x.val.getComputedTextLength()));
    const max = Math.max(...rows.map((r) => r.prefill_tokens_b));
    const u = (Math.max(60, W - labelW - 12) * unit) / max;
    const pts = [];
    groups.forEach(({ g, val, r }, i) => {
      const w = (r.prefill_tokens_b / unit) * u;
      for (let k = 0; k * u < w - 0.5; k++) {
        const bx = k * u, last = (k + 1) * u >= w - 0.5, bw = Math.min(u, w - bx) - (last ? 0 : 2);
        const d = last ? barPath(bx, 23, Math.max(bw, 1.5), 24, 4) : `M${bx} 23h${bw}v24h-${bw}z`;
        const p = el('path', { d, style: `fill:${COLOR[r.router]};--i:${k + i}`, class: 'ap' }, g);
        if (bw < 0) p.remove();
      }
      val.setAttribute('x', w + 10);
      pts.push({ box: { x: 0, y: i * rowH, w: W, h: rowH - 10 }, title: LABEL[r.router], lines: [
        ['prefill tokens', bn(r.prefill_tokens_b)], ['session affinity', ratio(r.prefill_vs_affinity)],
        ['prefix reuse', pct(r.prefix_reuse_pct)], ['runs meet the SLA', `${r.units_meeting_sla} of ${r.units}`],
      ] });
    });
    interact(svg, pts, { quiet: true });
  }

  // Schematic of one routing decision. Worker 2 holds the session's cached prefix and two other sessions;
  // worker 4 is idle. The loads are the same in all four panels.
  function routing(host) {
    const router = host.dataset.router;
    const load = [1, 2, 1, 0], cached = 1, target = { rr: 2, kv: 3, kvp16: 1, aff: 1 }[router];
    const reuse = target === cached;
    const W = widthOf(host), H = 168, gap = 8, bw = (W - 3 * gap) / 4, top = 50, bh = 80;
    const outcome = reuse ? 'reuses the cached prefix' : 'recomputes the prefix';
    const why = { rr: 'next worker in turn', kv: 'lowest prefill plus decode load', kvp16: 'prefill outweighs decode load', aff: "the session's own worker" }[router];
    const svg = start(host, W, H, `${LABEL[router]}: the session's next call goes to worker ${target + 1} (${why}) and ${outcome}.`);
    const cx = (i) => i * (bw + gap) + bw / 2;
    for (let i = 0; i < 4; i++) {
      const x = i * (bw + gap);
      el('rect', { x: x + 0.5, y: top + 0.5, width: bw - 1, height: bh - 1, rx: 4, style: `fill:none;stroke:${i === target ? COLOR[router] : 'var(--axis)'};stroke-width:${i === target ? 2 : 1}` }, svg);
      for (let k = 0; k < load[i]; k++) el('rect', { x: x + 7, y: top + 8 + k * 13, width: bw - 14, height: 9, rx: 2, style: `fill:${NEUTRAL}` }, svg);
      if (i === cached) el('rect', { x: x + 7, y: top + bh - 25, width: bw - 14, height: 18, rx: 2, style: `fill:${INK}` }, svg);
      if (i === target && !reuse) el('rect', { x: x + 7.75, y: top + bh - 24.25, width: bw - 15.5, height: 16.5, rx: 2, style: 'fill:none;stroke:var(--ink-3);stroke-width:1.5' }, svg);
      text(svg, cx(i), top + bh + 15, `W${i + 1}`, { 'text-anchor': 'middle' });
    }
    // The call enters above the worker that last served the session and bends to its target.
    const sx = cx(cached), tx = cx(target), y0 = 16, y1 = top - 4;
    el('circle', { cx: sx, cy: y0, r: 4.5, style: `fill:${COLOR[router]}` }, svg);
    const d = sx === tx ? `M${sx} ${y0}V${y1}` : `M${sx} ${y0}V${y0 + 10}Q${sx} ${y0 + 18} ${sx + Math.sign(tx - sx) * 8} ${y0 + 18}H${tx - Math.sign(tx - sx) * 8}Q${tx} ${y0 + 18} ${tx} ${y0 + 26}V${y1}`;
    el('path', { d, style: `fill:none;stroke:${COLOR[router]};stroke-width:2;stroke-linejoin:round` }, svg);
    el('path', { d: `M${tx - 5} ${y1 - 6}L${tx} ${y1}L${tx + 5} ${y1 - 6}`, style: `fill:none;stroke:${COLOR[router]};stroke-width:2;stroke-linecap:round;stroke-linejoin:round` }, svg);
    text(svg, sx + 10, y0 + 4, 'next call', { class: 'mid', 'text-anchor': sx > W / 2 ? 'end' : 'start', dx: sx > W / 2 ? -20 : 0 });
    const out = text(svg, 0, H - 4, outcome, { class: 'lab strong' });
    out.setAttribute('x', Math.max(0, Math.min(W - out.getComputedTextLength(), tx - out.getComputedTextLength() / 2)));
  }

  // Horizontal bars: prefill tokens per router, value and SLA count at the bar end. Both panels share one scale.
  function bars(host, D) {
    const scope = host.dataset.scope, rows = routerRows(D, scope);
    const W = widthOf(host), rowH = 50, H = rows.length * rowH - 8;
    const unit = scope === 'windows' ? 'windows' : 'runs';
    const svg = start(host, W, H, `Prefill tokens by router: ${rows.map((r) => `${LABEL[r.router]} ${bn(r.prefill_tokens_b)}, ${r.units_meeting_sla} of ${r.units} ${unit} meet the SLA`).join('; ')}.`);
    const groups = rows.map((r, i) => {
      const g = el('g', { transform: `translate(0,${i * rowH})` }, svg);
      text(g, 0, 13, LABEL[r.router], { class: 'lab' });
      const val = text(g, 0, 36, '', {});
      const a = el('tspan', { class: 'strong', 'font-size': 13 }, val); a.textContent = bn(r.prefill_tokens_b);
      const b = el('tspan', { dx: 9 }, val); b.textContent = `SLA ${r.units_meeting_sla} of ${r.units}`;
      return { g, val, r };
    });
    const labelW = Math.max(...groups.map((x) => x.val.getComputedTextLength()));
    const max = Math.max(...D.routers.filter((r) => r.scope === 'all' || r.scope === 'windows').map((r) => r.prefill_tokens_b));
    const span = Math.max(30, W - labelW - 12);
    const pts = [];
    groups.forEach(({ g, val, r }, i) => {
      const w = Math.max(2, (r.prefill_tokens_b / max) * span);
      el('path', { d: barPath(0, 22, w, 20, 4), style: `fill:${COLOR[r.router]};--i:${i}`, class: 'gx' }, g);
      val.setAttribute('x', w + 9);
      pts.push({ box: { x: 0, y: i * rowH, w: W, h: rowH - 6 }, title: LABEL[r.router], lines: [
        ['prefill tokens', bn(r.prefill_tokens_b)], ['session affinity', ratio(r.prefill_vs_affinity)], ['prefix reuse', pct(r.prefix_reuse_pct)],
        [`${unit} meet the SLA`, `${r.units_meeting_sla} of ${r.units}`], ['of requests meet the SLA', pct(r.requests_meeting_sla_pct)],
      ] });
    });
    interact(svg, pts, { quiet: true });
  }

  // One square per run or window under each router, ordered by peak concurrent trials.
  function units(host, D) {
    const scope = host.dataset.scope, isWin = scope === 'windows';
    const src = (isWin ? D.windows : D.runs).slice().sort((a, b) => a.peak_trials - b.peak_trials || (a.unit < b.unit ? -1 : 1));
    const n = src.length, W = widthOf(host), gap = 2;
    let rpc = 1, cell = Math.min(16, Math.floor((W - (n - 1) * gap) / n));
    if (!isWin) {
      for (rpc of [3, 4, 6, 8, 9, 12]) { cell = Math.floor((W + gap) / Math.ceil(n / rpc)) - gap; if (cell >= 7) break; }
      cell = Math.min(cell, 11);
    } else if (cell < 9) { rpc = 2; cell = Math.min(16, Math.floor((W + gap) / Math.ceil(n / rpc)) - gap); }
    const cols = Math.ceil(n / rpc), gridW = cols * (cell + gap) - gap, gridH = rpc * (cell + gap) - gap;
    const blockH = 22 + gridH + 16, H = ROUTERS.length * blockH + 14;
    const counts = ROUTERS.map((r) => src.filter((u) => u[`sla_${r}`] === 'meets').length);
    const noun = isWin ? 'windows' : 'runs';
    const svg = start(host, W, H, `${isWin ? 'Endpoint windows' : 'Runs'} meeting the SLA: ${ROUTERS.map((r, i) => `${LABEL[r]} ${counts[i]} of ${n}`).join('; ')}.`);
    const pts = [];
    ROUTERS.forEach((r, ri) => {
      const y0 = ri * blockH;
      const lab = text(svg, 0, y0 + 13, isWin ? SHORT[r] : LABEL[r], { class: 'lab' });
      const cnt = text(svg, Math.max(gridW, 120), y0 + 13, '', { 'text-anchor': 'end' });
      const a = el('tspan', { class: 'strong' }, cnt); a.textContent = `${counts[ri]}`;
      const b = el('tspan', {}, cnt); b.textContent = ` of ${n}`;
      if (lab.getComputedTextLength() + cnt.getComputedTextLength() + 10 > Math.max(gridW, 120)) lab.textContent = SHORT[r];
      src.forEach((u, i) => {
        const c = Math.floor(i / rpc), row = i % rpc, x = c * (cell + gap), y = y0 + 22 + row * (cell + gap);
        const meets = u[`sla_${r}`] === 'meets';
        el('rect', { x, y, width: cell, height: cell, rx: 1.5, style: `fill:${meets ? COLOR[r] : INK};--i:${c}`, class: 'ap' }, svg);
        pts.push({ box: { x: x - 1, y: y - 1, w: cell + 2, h: cell + 2 }, title: u.unit, lines: [
          [`of requests meet the SLA, ${SHORT[r]}`, share(u[`sla_share_${r}_pct`]), COLOR[r]], ['peak concurrent trials', int(u.peak_trials)],
          ['p99 TTFT', ms(u[`ttft_p99_${r}_ms`])], ['traffic', u.traffic], [isWin ? 'endpoint' : 'harness', isWin ? u.endpoint : u.harness],
        ] });
      });
    });
    const yA = H - 3;
    text(svg, 0, yA, `${int(src[0].peak_trials)} peak`, {});
    text(svg, gridW, yA, `${int(src[n - 1].peak_trials)} peak trials`, { 'text-anchor': 'end' });
    interact(svg, pts);
  }

  // Rows with one or more panels on a shared set of rows: dumbbells, dots and bars.
  // cfg.rows: [{label, color?, mono?}], cfg.panels: [{title, titleShort (used when the title does not fit), domain, log, ticks, fmt, ref, marks(row), link, bar, text(row), tip(row)}]
  function rowPanels(host, cfg) {
    const W = widthOf(host), rows = cfg.rows, n = cfg.panels.length;
    const side = W >= (cfg.wideAt || 680), across = side && !cfg.stack;
    const svg = start(host, W, 10, cfg.label);
    const probe = rows.map((r) => text(svg, 0, -50, r.label, { class: 'lab' }));
    const lw = side ? Math.min(cfg.maxLabel || 250, Math.max(...probe.map((t) => t.getComputedTextLength())) + (cfg.swatch ? 16 : 0)) + 16 : 0;
    probe.forEach((t) => t.remove());
    const hasRef = cfg.panels.some((p) => p.ref);
    const rowH = (cfg.rowH || 30) + (side ? 0 : 18), headH = hasRef ? 46 : 30, axisH = 24, gap = 34;
    const blocks = [];
    let H;
    if (across) {
      const pw = (W - lw - gap * (n - 1)) / n;
      cfg.panels.forEach((p, i) => blocks.push({ p, x0: lw + i * (pw + gap), x1: lw + i * (pw + gap) + pw, y0: headH, labels: i === 0 }));
      H = headH + rows.length * rowH + axisH;
    } else {
      let y = 0;
      cfg.panels.forEach((p) => { blocks.push({ p, x0: lw, x1: W, y0: y + headH, labels: true }); y += headH + rows.length * rowH + axisH + 22; });
      H = y - 22;
    }
    resize(svg, W, H);
    const pts = [];
    for (const b of blocks) {
      const p = b.p, padL = 8, padR = p.text ? (p.textW || 96) + 12 : 14;
      const r0 = b.x0 + padL, r1 = b.x1 - padR;
      const x = p.log ? logScale(p.domain[0], p.domain[1], r0, r1) : lin(p.domain[0], p.domain[1], r0, r1);
      const yb = b.y0 + rows.length * rowH;
      const head = text(svg, b.x0, b.y0 - (hasRef ? 28 : 12), p.title, { class: 'head' });
      if (p.titleShort && head.getComputedTextLength() > (across ? b.x1 : W) - b.x0) head.textContent = p.titleShort;
      const band = cfg.rowH || 30;
      const rule = (v, attrs) => {
        if (side) el('line', Object.assign({ x1: x(v), x2: x(v), y1: b.y0 + (attrs.style ? -5 : 0), y2: yb }, attrs), svg);
        else rows.forEach((_, j) => el('line', Object.assign({ x1: x(v), x2: x(v), y1: b.y0 + (j + 1) * rowH - band + 3, y2: b.y0 + (j + 1) * rowH - 3 }, attrs), svg));
      };
      let edge = -Infinity;
      for (const v of p.ticks) {
        rule(v, { class: v === p.baseline ? 'base' : 'grid' });
        const t = clamp(text(svg, x(v), yb + 15, p.fmt(v), { 'text-anchor': 'middle' }), b.x0, b.x1), w = t.getComputedTextLength();
        const left = t.getAttribute('text-anchor') === 'start' ? b.x0 : t.getAttribute('text-anchor') === 'end' ? b.x1 - w : x(v) - w / 2;
        if (left < edge + 6) t.remove(); else edge = left + w;
      }
      if (p.ref) {
        rule(p.ref.v, { style: `stroke:${INK}` });
        const t = text(svg, x(p.ref.v) + 5, b.y0 - 8, p.ref.label, { class: 'mid' });
        if (x(p.ref.v) + 5 + t.getComputedTextLength() > b.x1) { t.setAttribute('text-anchor', 'end'); t.setAttribute('x', x(p.ref.v) - 5); }
      }
      rows.forEach((row, j) => {
        const top = b.y0 + j * rowH, cy = top + rowH - (cfg.rowH || 30) / 2;
        if (b.labels) {
          const lx = cfg.swatch && row.color ? 15 : 0;
          if (cfg.swatch && row.color) el('rect', { x: 0, y: (side ? cy : top + 10) - 5, width: 10, height: 10, rx: 2, style: `fill:${row.color}`, opacity: row.opacity || 1 }, svg);
          text(svg, lx, side ? cy + 4 : top + 14, row.label, { class: row.mono ? 'mid' : 'lab' });
        }
        if (j > 0 && !side) el('line', { x1: b.x0, x2: b.x1, y1: top, y2: top, class: 'grid' }, svg);
        const marks = p.marks(row).filter((m) => m.v != null);
        const xs = marks.map((m) => x(m.v));
        const lo = Math.min(...xs), hi = Math.max(...xs);
        if (p.bar) {
          const base = x(p.baseline != null ? p.baseline : p.domain[0]);
          marks.forEach((m) => el('path', { d: barPath(base, cy - 7, Math.max(2, x(m.v) - base), 14, 4), style: `fill:${m.color};--i:${j}`, opacity: m.opacity || 1, class: 'gx' }, svg));
        } else {
          if (p.link && hi - lo > 1) el('line', { x1: lo, x2: hi, y1: cy, y2: cy, style: 'stroke:var(--axis);stroke-width:2' }, svg);
          marks.forEach((m) => mark(svg, m.shape || 'dot', x(m.v), cy, m.color, { opacity: m.opacity }));
        }
        if (p.text && marks.length) {
          text(svg, b.x1, cy + 4, p.text(row), { class: 'mid', 'text-anchor': 'end' });
        }
        pts.push({ box: { x: b.labels ? 0 : b.x0, y: top, w: b.x1 - (b.labels ? 0 : b.x0), h: rowH }, title: row.tipTitle || row.label, lines: p.tip(row) });
      });
    }
    interact(svg, pts, { quiet: true });
  }

  const logTicks = [100, 1000, 10000, 100000, 1000000];
  const logFmt = (v) => (v < 1000 ? `${v} ms` : `${int(v / 1000)} s`);

  // Mean TTFT and median p99 TTFT by router, for all runs and for the endpoint windows.
  function latency(host, D) {
    const panel = (scope, title, unit) => {
      const get = (row) => D.routers.find((x) => x.scope === scope && x.router === row.router);
      return {
        title, log: true, domain: [50, 1500000], ticks: logTicks, fmt: logFmt, ref: { v: SLA_TTFT_MS, label: '2 s bound' }, link: true, textW: 118,
        marks: (row) => [{ v: get(row).mean_ttft_ms, color: row.color }, { v: get(row).median_unit_p99_ttft_ms, color: row.color, shape: 'ring' }],
        text: (row) => `${ms(get(row).mean_ttft_ms)} / ${ms(get(row).median_unit_p99_ttft_ms)}`,
        tip: (row) => [['mean TTFT', ms(get(row).mean_ttft_ms)], [`median ${unit} p99 TTFT`, ms(get(row).median_unit_p99_ttft_ms)], [`worst ${unit} p99 TTFT`, ms(get(row).worst_unit_p99_ttft_ms)]],
      };
    };
    const a = routerRows(D, 'all');
    rowPanels(host, {
      label: `Time to first token by router. All runs: ${a.map((r) => `${LABEL[r.router]} mean ${ms(r.mean_ttft_ms)}, median run p99 ${ms(r.median_unit_p99_ttft_ms)}`).join('; ')}.`,
      rows: ROUTERS.map((r) => ({ router: r, label: LABEL[r], color: COLOR[r] })), swatch: true, rowH: 34, stack: true,
      panels: [panel('all', `All ${int(D.study[0].runs)} runs, mean / median p99`, 'run'), panel('windows', `${int(D.study[0].windows)} endpoint windows, mean / median p99`, 'window')],
    });
  }

  // Share of requests meeting the SLA in each endpoint window, by router.
  function heat(host, D) {
    const rows = D.windows, W = widthOf(host), rowH = 38, headH = 30;
    const svg = start(host, W, 10, `Share of requests meeting the SLA in ${rows.length} endpoint windows. ${ROUTERS.map((r) => `${LABEL[r]}: ${rows.filter((w) => w[`sla_${r}`] === 'meets').length} of ${rows.length} windows at 99% or more`).join('; ')}.`);
    const sub = (r) => `${utc(r.start_unix).slice(5)}, ${int(r.peak_trials)} peak`;
    const probe = rows.flatMap((r) => [text(svg, 0, -50, family(r.traffic), { class: 'lab' }), text(svg, 0, -50, sub(r), {})]);
    const lw = Math.max(...probe.map((t) => t.getComputedTextLength())) + 14;
    probe.forEach((t) => t.remove());
    const cw = Math.min(150, (W - lw) / 4), H = headH + rows.length * rowH + 62;
    resize(svg, W, H);
    const all = rows.flatMap((r) => ROUTERS.map((p) => r[`sla_share_${p}_pct`]));
    const lo = Math.floor(Math.min(...all) / 5) * 5, t = (v) => (v - lo) / (100 - lo);
    const fill = (v) => `fill:color-mix(in oklab, var(--seq-hi) ${(100 * t(v)).toFixed(1)}%, var(--seq-lo))`;
    ROUTERS.forEach((p, i) => {
      const x = lw + i * cw;
      text(svg, x + (cw - 2) / 2, 14, cw >= 92 ? SHORT[p] : TINY[p], { class: 'lab', 'text-anchor': 'middle' });
      el('rect', { x, y: headH - 8, width: cw - 2, height: 4, rx: 2, style: `fill:${COLOR[p]}` }, svg);
    });
    const pts = [];
    rows.forEach((r, j) => {
      const y = headH + j * rowH;
      text(svg, 0, y + 15, family(r.traffic), { class: 'lab' });
      text(svg, 0, y + 29, sub(r), {});
      ROUTERS.forEach((p, i) => {
        const v = r[`sla_share_${p}_pct`], x = lw + i * cw, meets = v >= SLA_SHARE, on = t(v) > 0.56 ? 'on-hi' : 'on-lo';
        el('rect', { x, y, width: cw - 2, height: rowH - 2, rx: 2, style: `${fill(v)};--i:${j * 4 + i}`, class: 'ap' }, svg);
        if (meets) el('path', { d: `M${x + cw / 2 - 6} ${y + rowH / 2 - 1}l4 4l7 -8`, style: `fill:none;stroke:var(--seq-${on === 'on-hi' ? 'on-hi' : 'on-lo'});stroke-width:1.75;stroke-linecap:round;stroke-linejoin:round` }, svg);
        else text(svg, x + cw / 2 - 1, y + rowH / 2 + 3, F1.format(v), { class: on, 'text-anchor': 'middle', 'font-weight': 500 });
        pts.push({ box: { x, y, w: cw - 2, h: rowH - 2 }, title: `${r.endpoint}, ${utc(r.start_unix)} UTC`, lines: [
          [`of requests meet the SLA, ${SHORT[p]}`, share(v), COLOR[p]], ['p99 TTFT', ms(r[`ttft_p99_${p}_ms`])],
          ['runs merged', int(r.merged_runs)], ['trials', int(r.trials)], ['peak concurrent trials', int(r.peak_trials)], ['workers', int(r.workers)],
        ] });
      });
    });
    // Scale: the ramp in steps, with the SLA threshold marked.
    const sy = headH + rows.length * rowH + 22, sw = Math.min(260, W - lw - 4), steps = 22;
    for (let k = 0; k < steps; k++) el('rect', { x: lw + (k * sw) / steps, y: sy, width: sw / steps + 0.5, height: 10, style: fill(lo + ((k + 0.5) / steps) * (100 - lo)) }, svg);
    const sx = (v) => lw + t(v) * sw;
    text(svg, lw, sy + 25, pct0(lo), {});
    text(svg, lw + sw, sy + 25, '100%', { 'text-anchor': 'end' });
    el('line', { x1: sx(SLA_SHARE), x2: sx(SLA_SHARE), y1: sy - 5, y2: sy + 14, style: `stroke:${INK};stroke-width:1.5` }, svg);
    text(svg, sx(SLA_SHARE) - 6, sy - 8, 'SLA threshold, 99%', { 'text-anchor': 'end', class: 'mid' });
    interact(svg, pts);
  }

  // Histogram of default-router prefill over affinity prefill, one count per run, misses stacked at the base.
  function ratioDist(host, D) {
    const rows = D.runs.filter((r) => r.kv_vs_aff_prefill != null), step = 0.25;
    const stat = D.routers.find((r) => r.scope === 'all' && r.router === 'kv');
    const bin = (v) => Math.floor(v / step + 1e-9);
    const b0 = Math.min(...rows.map((r) => bin(r.kv_vs_aff_prefill))), b1 = Math.max(...rows.map((r) => bin(r.kv_vs_aff_prefill)));
    const bins = [];
    for (let b = b0; b <= b1; b++) {
      const inBin = rows.filter((r) => bin(r.kv_vs_aff_prefill) === b);
      bins.push({ lo: b * step, hi: (b + 1) * step, n: inBin.length, miss: inBin.filter((r) => r.sla_kv === 'misses').length });
    }
    const W = widthOf(host), H = Math.round(Math.max(260, Math.min(340, W * 0.4))), m = { t: 56, r: 10, b: 40, l: 34 };
    const x = lin(b0 * step, (b1 + 1) * step, m.l, W - m.r), yt = ticks(Math.max(...bins.map((b) => b.n)), 4), y = lin(0, yt[yt.length - 1], H - m.b, m.t);
    const svg = start(host, W, H, `Histogram of the ${rows.length} runs by default-router prefill relative to affinity. The median run is at ${ratio(stat.prefill_vs_affinity_run_median)} and the 90th-percentile run at ${ratio(stat.prefill_vs_affinity_run_p90)}.`);
    for (const v of yt) {
      el('line', { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), class: v ? 'grid' : 'base' }, svg);
      text(svg, m.l - 7, y(v) + 4, int(v), { 'text-anchor': 'end' });
    }
    for (let v = Math.ceil(b0 * step); v <= (b1 + 1) * step; v++) text(svg, x(v), H - m.b + 16, `${v}x`, { 'text-anchor': 'middle' });
    text(svg, (m.l + W - m.r) / 2, H - 5, 'Default-router prefill divided by affinity prefill', { 'text-anchor': 'middle' });
    text(svg, 0, m.t - 9, 'Runs', {});
    const bw = Math.min(24, x(step) - x(0) - 2), pts = [];
    bins.forEach((b, i) => {
      const cx = x((b.lo + b.hi) / 2), base = y(0);
      const hm = base - y(b.miss), hn = base - y(b.n);
      if (b.miss) el('path', { d: b.miss === b.n ? colPath(cx - bw / 2, base, bw, Math.max(hm, 2), 3) : `M${cx - bw / 2} ${base}v-${Math.max(hm, 2)}h${bw}v${Math.max(hm, 2)}z`, style: `fill:${INK};--i:${i}`, class: 'gy' }, svg);
      if (b.n > b.miss) {
        const off = b.miss ? Math.max(hm, 2) + 2 : 0;
        el('path', { d: colPath(cx - bw / 2, base - off, bw, Math.max(hn - off, 2), 3), style: `fill:${COLOR.kv};--i:${i}`, class: 'gy' }, svg);
      }
      if (b.n) pts.push({ x: cx, y: y(b.n), box: { x: x(b.lo), y: m.t, w: x(b.hi) - x(b.lo), h: H - m.b - m.t }, title: `${F2.format(b.lo)}-${F2.format(b.hi)}x`, lines: [
        ['runs', int(b.n), COLOR.kv], ['of them miss the SLA with the default KV router', int(b.miss), INK],
      ] });
    });
    const flag = (v, label, yy, limit) => {
      el('line', { x1: x(v), x2: x(v), y1: yy - 9, y2: H - m.b, style: `stroke:${INK}` }, svg);
      const t = text(svg, x(v) + 6, yy, label, { class: 'strong' });
      if (x(v) + 6 + t.getComputedTextLength() > limit - 4) { t.setAttribute('x', x(v) - 6); t.setAttribute('text-anchor', 'end'); }
    };
    flag(stat.prefill_vs_affinity_run_median, `median ${ratio(stat.prefill_vs_affinity_run_median)}`, 11, W);
    flag(stat.prefill_vs_affinity_run_p90, `90th percentile ${ratio(stat.prefill_vs_affinity_run_p90)}`, 28, W);
    interact(svg, pts, { quiet: true });
  }

  // One mark per run: default-router prefill over affinity prefill, against peak concurrent trials.
  function scatter(host, D) {
    const rows = D.runs.filter((r) => r.kv_vs_aff_prefill != null);
    const W = widthOf(host), H = Math.round(Math.max(260, Math.min(400, W * 0.46)));
    const m = { t: 14, r: 12, b: 40, l: 34 };
    const xt = ticks(Math.max(...rows.map((r) => r.peak_trials)), Math.max(3, Math.floor(W / 120))), yt = ticks(Math.max(...rows.map((r) => r.kv_vs_aff_prefill)), 4);
    const x = lin(0, xt[xt.length - 1], m.l + 6, W - m.r), y = lin(0, yt[yt.length - 1], H - m.b, m.t);
    const misses = rows.filter((r) => r.sla_kv === 'misses').length;
    const svg = start(host, W, H, `Scatter of ${rows.length} runs. Default-router prefill relative to affinity rises with peak concurrent trials. The default KV router misses the SLA on ${misses} runs.`);
    for (const v of yt) {
      el('line', { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), class: v === 1 || v === 0 ? 'base' : 'grid' }, svg);
      text(svg, m.l - 7, y(v) + 4, `${v}x`, { 'text-anchor': 'end' });
    }
    for (const v of xt) clamp(text(svg, x(v), H - m.b + 16, int(v), { 'text-anchor': 'middle' }), 0, W);
    text(svg, (m.l + W - m.r) / 2, H - 5, 'Peak concurrent trials', { 'text-anchor': 'middle' });
    text(svg, W - m.r, y(1) + 14, 'equal prefill', { 'text-anchor': 'end' });
    const pts = rows.map((r) => ({ r, x: x(r.peak_trials), y: y(r.kv_vs_aff_prefill) }));
    for (const p of pts.slice().sort((a, b) => (a.r.sla_kv === 'misses') - (b.r.sla_kv === 'misses'))) {
      if (p.r.sla_kv === 'misses') el('path', { d: diamond(p.x, p.y, 5.5), style: `fill:${INK};stroke:${PAPER};stroke-width:1.5`, class: 'ap' }, svg);
      else el('circle', { cx: p.x, cy: p.y, r: 4, style: `fill:${COLOR.kv};fill-opacity:0.85;stroke:${PAPER};stroke-width:1.5`, class: 'ap' }, svg);
      const r = p.r;
      p.title = r.unit;
      p.lines = [
        ['default / affinity prefill', ratio(r.kv_vs_aff_prefill)], ['peak trials', int(r.peak_trials)],
        [`workers (${r.gpus} GPUs)`, int(r.workers)], ['harness', r.harness], ['traffic', r.traffic],
        ['the SLA, default KV router', r.sla_kv], ['the SLA, affinity', r.sla_aff],
      ];
    }
    pts.sort((a, b) => a.x - b.x || a.y - b.y);
    interact(svg, pts);
  }

  // Four traffic sources: prefill, runs meeting the SLA, and provider cache against simulated reuse.
  function traffic(host, D) {
    const fam = (row, router) => D.routers.find((x) => x.scope_label === row.traffic && x.router === router);
    rowPanels(host, {
      label: `Default KV router against session affinity by traffic source. ${D.traffic.map((t) => `${t.traffic}: default-router prefill ${ratio(t.kv_vs_aff_prefill)} affinity, ${t.sla_kv} and ${t.sla_aff} of ${t.runs} runs meet the SLA, provider cached ${pct(t.provider_cached_pct)}, simulated affinity reuse ${pct(t.aff_reuse_pct)}`).join('; ')}.`,
      rows: D.traffic.map((t) => Object.assign({ label: t.traffic }, t)), rowH: 30, wideAt: 620, stack: true,
      panels: [{
        title: 'Prefill tokens, billions', domain: [0, 9], ticks: [0, 3, 6, 9], baseline: 0, fmt: (v) => `${v}`, link: true, textW: 104,
        marks: (r) => [{ v: fam(r, 'aff').prefill_tokens_b, color: COLOR.aff }, { v: fam(r, 'kv').prefill_tokens_b, color: COLOR.kv }],
        text: (r) => ratio(r.kv_vs_aff_prefill),
        tip: (r) => [['prefill, default KV router', bn(fam(r, 'kv').prefill_tokens_b), COLOR.kv], ['prefill, affinity', bn(fam(r, 'aff').prefill_tokens_b), COLOR.aff], ['default / affinity', ratio(r.kv_vs_aff_prefill)]],
      }, {
        title: 'Runs meeting the SLA', domain: [70, 100], ticks: [70, 80, 90, 100], fmt: pct0, link: true, textW: 104,
        marks: (r) => [{ v: (100 * r.sla_kv) / r.runs, color: COLOR.kv }, { v: (100 * r.sla_aff) / r.runs, color: COLOR.aff }],
        text: (r) => `${r.sla_kv} to ${r.sla_aff} of ${r.runs}`,
        tip: (r) => ROUTERS.map((p) => [`runs meet the SLA, ${SHORT[p]}`, `${r[`sla_${p}`]} of ${r.runs}`, COLOR[p]]),
      }, {
        title: 'Prompt tokens served from cache', domain: [70, 100], ticks: [70, 80, 90, 100], fmt: pct0, link: true, textW: 104,
        text: (r) => `${pct(r.provider_cached_pct)} / ${pct(r.aff_reuse_pct)}`,
        marks: (r) => [{ v: r.provider_cached_pct, color: INK, shape: 'ring' }, { v: r.aff_reuse_pct, color: COLOR.aff }],
        tip: (r) => [['recorded at the provider', pct(r.provider_cached_pct), INK], ['simulated, session affinity', pct(r.aff_reuse_pct), COLOR.aff], ['simulated, default KV router', pct(fam(r, 'kv').prefix_reuse_pct), COLOR.kv]],
      }],
    });
  }

  // Harness versions: runs meeting the SLA under the default router and affinity, and the prefill gap.
  function harness(host, D) {
    const share = (r, k) => (100 * r[k]) / r.runs;
    const rows = D.harness.slice().sort((a, b) => (share(b, 'sla_aff') - share(b, 'sla_kv')) - (share(a, 'sla_aff') - share(a, 'sla_kv')) || b.kv_vs_aff_prefill - a.kv_vs_aff_prefill);
    rowPanels(host, {
      label: `Runs meeting the SLA by harness version, default KV router and session affinity: ${rows.map((r) => `${r.harness} ${r.sla_kv} and ${r.sla_aff} of ${r.runs}`).join('; ')}.`,
      rows: rows.map((r) => Object.assign({ label: r.harness, mono: true }, r)), rowH: 26, maxLabel: 260, wideAt: 640,
      panels: [{
        title: 'Runs meeting the SLA', domain: [60, 100], ticks: [60, 70, 80, 90, 100], fmt: pct0, link: true, textW: 108,
        marks: (r) => [{ v: share(r, 'sla_kv'), color: COLOR.kv }, { v: share(r, 'sla_aff'), color: COLOR.aff }],
        text: (r) => (r.sla_kv === r.sla_aff ? `${r.sla_aff} of ${r.runs}` : `${r.sla_kv} to ${r.sla_aff} of ${r.runs}`),
        tip: (r) => ROUTERS.map((p) => [`runs meet the SLA, ${SHORT[p]}`, `${r[`sla_${p}`]} of ${r.runs}`, COLOR[p]]),
      }, {
        title: 'Default-router prefill, multiple of affinity', domain: [0, 4], ticks: [0, 1, 2, 3, 4], baseline: 0, fmt: (v) => `${v}x`, bar: true, textW: 40,
        ref: { v: 1, label: 'equal' },
        marks: (r) => [{ v: r.kv_vs_aff_prefill, color: COLOR.kv }],
        text: (r) => ratio(r.kv_vs_aff_prefill),
        tip: (r) => [['prefill, default KV router', `${bn2(r.prefill_kv_b)}B`, COLOR.kv], ['prefill, affinity', `${bn2(r.prefill_aff_b)}B`, COLOR.aff], ['default / affinity', ratio(r.kv_vs_aff_prefill)], ['requests', int(r.requests)]],
      }],
    });
  }

  // Prefix reuse against worker count on a 100-trial slice, one line per router.
  function pool(host, D) {
    const trace = host.dataset.trace, routers = ['rr', 'kv', 'aff'];
    const rows = D.pilot.filter((r) => r.trace === trace && routers.includes(r.router));
    const workers = [...new Set(rows.map((r) => r.workers))].sort((a, b) => a - b);
    const W = widthOf(host), H = 236, m = { t: 14, r: 18, b: 40, l: 40 };
    const lo = 60, hi = 100;
    const x = (w) => m.l + 10 + (workers.indexOf(w) / (workers.length - 1)) * (W - m.l - m.r - 10);
    const y = lin(lo, hi, H - m.b, m.t);
    const end = (r) => rows.find((p) => p.router === r && p.workers === workers[workers.length - 1]);
    const svg = start(host, W, H, `Prefix reuse by worker count. At ${workers[workers.length - 1]} workers: ${routers.map((r) => `${LABEL[r]} ${pct(end(r).prefix_reuse_pct)}`).join(', ')}.`);
    for (const v of [60, 70, 80, 90, 100]) {
      el('line', { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), class: v === lo ? 'base' : 'grid' }, svg);
      text(svg, m.l - 7, y(v) + 4, `${v}%`, { 'text-anchor': 'end' });
    }
    for (const w of workers) text(svg, x(w), H - m.b + 16, String(w), { 'text-anchor': 'middle' });
    text(svg, (m.l + W - m.r) / 2, H - 5, 'Workers', { 'text-anchor': 'middle' });
    for (const r of routers) {
      const pts = rows.filter((p) => p.router === r).sort((a, b) => a.workers - b.workers);
      const path = el('path', { d: pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.workers)} ${y(p.prefix_reuse_pct)}`).join(''), style: `fill:none;stroke:${COLOR[r]};stroke-width:2;stroke-linejoin:round;stroke-linecap:round`, class: 'dr' }, svg);
      path.style.setProperty('--len', Math.ceil(path.getTotalLength()));
      for (const p of pts) el('circle', { cx: x(p.workers), cy: y(p.prefix_reuse_pct), r: 4, style: `fill:${COLOR[r]};stroke:${PAPER};stroke-width:2`, class: 'ap' }, svg);
    }
    const rrEnd = end('rr');
    text(svg, x(rrEnd.workers) - 9, y(rrEnd.prefix_reuse_pct) + 17, `Round-robin ${pct(rrEnd.prefix_reuse_pct)}`, { 'text-anchor': 'end', class: 'mid' });
    const pts = workers.map((w) => ({ x: x(w), y: m.t, title: `${w} workers (${2 * w} GPUs)`, lines: routers.map((r) => rows.find((p) => p.router === r && p.workers === w)).filter(Boolean)
      .map((p) => [`${SHORT[p.router]}, ${m1(p.prefill_tokens_m)} prefill`, pct(p.prefix_reuse_pct), COLOR[p.router]]) }));
    interact(svg, pts, { cross: [m.t, H - m.b] });
  }

  // The two pilot runs replayed in full: p99 TTFT and prefill tokens for every pool size and router.
  function pilotFull(host, D) {
    const trace = host.dataset.trace;
    const rows = D.pilot.filter((r) => r.trace === trace).sort((a, b) => a.workers - b.workers || ORDER.indexOf(a.router) - ORDER.indexOf(b.router));
    const maxP = Math.max(...rows.map((r) => r.prefill_tokens_m)), pt = ticks(maxP, 3);
    rowPanels(host, {
      label: `${rows[0].trace_label}: ${rows.map((r) => `${r.gpus} GPUs, ${LABEL[r.router]}: p99 TTFT ${ms(r.ttft_p99_ms)}, prefill ${m1(r.prefill_tokens_m)}`).join('; ')}.`,
      rows: rows.map((r) => Object.assign({ label: `${r.gpus} GPUs, ${SHORT[r.router]}`, tipTitle: `${r.gpus} GPUs, ${LABEL[r.router]}`, color: COLOR[r.router], opacity: r.router === 'kvp4' ? 0.5 : 1 }, r)),
      swatch: true, rowH: 28, wideAt: 640,
      panels: [{
        title: 'p99 TTFT', log: true, domain: [100, 1500000], ticks: logTicks, fmt: logFmt, ref: { v: SLA_TTFT_MS, label: '2 s bound' }, textW: 62,
        marks: (r) => [{ v: r.ttft_p99_ms, color: r.color, opacity: r.opacity }],
        text: (r) => ms(r.ttft_p99_ms),
        tip: (r) => [['p99 TTFT', ms(r.ttft_p99_ms)], ['mean TTFT', ms(r.ttft_mean_ms)], ['p99 ITL', ms(r.itl_p99_ms)], ['median trial', min1(r.median_trial_min)]],
      }, {
        title: 'Prefill tokens, millions', domain: [0, pt[pt.length - 1]], ticks: pt, baseline: 0, fmt: int, bar: true, textW: 62,
        marks: (r) => [{ v: r.prefill_tokens_m, color: r.color, opacity: r.opacity }],
        text: (r) => m1(r.prefill_tokens_m),
        tip: (r) => [['prefill tokens', m1(r.prefill_tokens_m)], ['prefix reuse', pct(r.prefix_reuse_pct)]],
      }],
    });
  }

  // flint endpoint: cache shares over time in the top panel, active trials in the bottom panel.
  function timeline(host, D) {
    const rows = D.timeline.map((r) => Object.assign({ t: Date.parse(r.bucket_start) }, r)).sort((a, b) => a.t - b.t);
    const step = 30 * 60 * 1000, t0 = rows[0].t, t1 = rows[rows.length - 1].t + step;
    const W = widthOf(host), m = { t: 34, r: 12, b: 38, l: 42 }, top = 180, gap = 36, bottom = 84, H = m.t + top + gap + bottom + m.b;
    const x = lin(t0, t1, m.l, W - m.r), y1 = lin(0, 100, m.t + top, m.t);
    const aMax = Math.max(...rows.map((r) => r.active_trials)), at = ticks(aMax, 2);
    const base2 = m.t + top + gap + bottom, y2 = lin(0, at[at.length - 1], base2, base2 - bottom);
    const low = rows.reduce((a, b) => (b.provider_cached_pct < a.provider_cached_pct ? b : a));
    const hhmm = (t) => new Date(t).toISOString().slice(11, 16), day = (t) => new Date(t).toISOString().slice(0, 10);
    const svg = start(host, W, H, `flint endpoint in 30-minute buckets. The share of prompt tokens served from cache falls from about 98% to ${pct(low.provider_cached_pct)} at ${hhmm(low.t)} UTC on ${day(low.t)}, while the reusable share stays at ${pct(Math.min(...rows.map((r) => r.reusable_pct)))} or more. Active trials peak at ${aMax}.`);
    text(svg, m.l, 12, 'Share of prompt tokens', { class: 'head' });
    text(svg, m.l, m.t + top + gap - 9, 'Active trials', { class: 'head' });
    for (const v of [0, 25, 50, 75, 100]) {
      el('line', { x1: m.l, x2: W - m.r, y1: y1(v), y2: y1(v), class: v ? 'grid' : 'base' }, svg);
      text(svg, m.l - 7, y1(v) + 4, `${v}%`, { 'text-anchor': 'end' });
    }
    for (const v of at) {
      el('line', { x1: m.l, x2: W - m.r, y1: y2(v), y2: y2(v), class: v ? 'grid' : 'base' }, svg);
      text(svg, m.l - 7, y2(v) + 4, int(v), { 'text-anchor': 'end' });
    }
    const every = W < 520 ? 4 : 2;
    for (let t = t0; t <= t1; t += every * 3600 * 1000) {
      clamp(text(svg, x(t), base2 + 16, hhmm(t), { 'text-anchor': 'middle' }), 0, W);
      if (t === t0 || hhmm(t) === '00:00') text(svg, x(t), base2 + 31, day(t), { 'text-anchor': t === t0 ? 'start' : 'middle' });
    }
    rows.forEach((r, i) => {
      const bw = Math.max(1, x(r.t + step) - x(r.t) - 2), h = base2 - y2(r.active_trials);
      el('path', { d: colPath(x(r.t) + 1, base2, bw, Math.max(h, 1), 3), style: `fill:${NEUTRAL};--i:${i * 2}`, class: 'gy' }, svg);
    });
    const mid = (r) => x(r.t + step / 2);
    const line = (key, color) => {
      const p = el('path', { d: rows.map((r, i) => `${i ? 'L' : 'M'}${mid(r)} ${y1(r[key])}`).join(''), style: `fill:none;stroke:${color};stroke-width:2;stroke-linejoin:round;stroke-linecap:round`, class: 'dr' }, svg);
      p.style.setProperty('--len', Math.ceil(p.getTotalLength()));
    };
    line('reusable_pct', NEUTRAL);
    line('provider_cached_pct', INK);
    el('circle', { cx: mid(low), cy: y1(low.provider_cached_pct), r: 4, style: `fill:${INK};stroke:${PAPER};stroke-width:2` }, svg);
    text(svg, mid(low), y1(low.provider_cached_pct) + 18, pct(low.provider_cached_pct), { 'text-anchor': 'middle', class: 'strong' });
    const pts = rows.map((r) => ({ x: mid(r), y: y1(r.provider_cached_pct), title: `${day(r.t)} ${hhmm(r.t)} UTC`, lines: [
      ['served from cache', pct(r.provider_cached_pct), INK], ['reusable', pct(r.reusable_pct), NEUTRAL],
      ['active trials', int(r.active_trials), NEUTRAL], ['calls', int(r.calls)],
    ] }));
    interact(svg, pts, { cross: [m.t, base2] });
  }

  // The native DeepSeek cross-check: one run on two simulated targets.
  function native(host, D) {
    const rows = D.native, maxP = Math.max(...rows.flatMap((r) => [r.native_prefill_tokens, r.target_prefill_tokens])) / 1e6, pt = ticks(maxP, 3);
    const maxT = Math.max(...rows.flatMap((r) => [r.native_ttft_p99_ms, r.target_ttft_p99_ms])), tt = ticks(maxT, 3);
    rowPanels(host, {
      label: `One DeepSeek run on two simulated targets. ${rows.map((r) => `${r.router_label}: prefill ${mInt(r.native_prefill_tokens / 1e6)} native and ${mInt(r.target_prefill_tokens / 1e6)} on the GLM-5.3-Flash target, p99 TTFT ${ms(r.native_ttft_p99_ms)} and ${ms(r.target_ttft_p99_ms)}`).join('; ')}.`,
      rows: rows.map((r) => Object.assign({ label: r.router_label, color: COLOR[r.router] }, r)), swatch: true, rowH: 32, wideAt: 620, stack: true,
      panels: [{
        title: 'Prefill tokens, millions, with the multiple of affinity on the native target', titleShort: 'Prefill tokens, millions, native target', domain: [0, pt[pt.length - 1]], ticks: pt, baseline: 0, fmt: int, link: true, textW: 136,
        marks: (r) => [{ v: r.target_prefill_tokens / 1e6, color: r.color, shape: 'ring' }, { v: r.native_prefill_tokens / 1e6, color: r.color }],
        text: (r) => ratio(r.native_prefill_vs_affinity),
        tip: (r) => [['prefill, native target', mInt(r.native_prefill_tokens / 1e6)], ['affinity, native target', ratio(r.native_prefill_vs_affinity)], ['prefill, GLM-5.3-Flash target', mInt(r.target_prefill_tokens / 1e6)], ['affinity, GLM-5.3-Flash target', ratio(r.target_prefill_vs_affinity)]],
      }, {
        title: 'p99 TTFT, native / GLM-5.3-Flash target', domain: [0, tt[tt.length - 1]], ticks: tt, baseline: 0, fmt: (v) => (v ? `${F1.format(v / 1000)} s` : '0'), ref: { v: SLA_TTFT_MS, label: '2 s bound' }, link: true, textW: 136,
        marks: (r) => [{ v: r.target_ttft_p99_ms, color: r.color, shape: 'ring' }, { v: r.native_ttft_p99_ms, color: r.color }],
        text: (r) => `${ms(r.native_ttft_p99_ms)} / ${ms(r.target_ttft_p99_ms)}`,
        tip: (r) => [['p99 TTFT, native target', ms(r.native_ttft_p99_ms)], ['p99 TTFT, GLM-5.3-Flash target', ms(r.target_ttft_p99_ms)], ['mean ITL, native target', `${F1.format(r.native_itl_mean_ms)} ms`], ['of requests meet the SLA, native target', pct(r.native_sla_share_pct)], ['of requests meet the SLA, GLM-5.3-Flash target', pct(r.target_sla_share_pct)]],
      }],
    });
  }

  // Slice check: sliced replay relative to the full replay, one dot per router.
  function slices(host, D) {
    const runs = [...new Set(D.slices.map((r) => r.run))];
    const diff = (a, b) => 100 * (a / b - 1);
    const of = (run) => ROUTERS.map((p) => D.slices.find((r) => r.run === run && r.router === p));
    const short = (run) => { const t = D.runs.find((r) => r.unit === run), parts = run.split('-'); return `${family(t ? t.traffic : run).split('-')[0]} ${parts[parts.length - 2]}, ${run.slice(4, 6)}-${run.slice(6, 8)}`; };
    const pMax = Math.max(...D.slices.map((r) => Math.abs(diff(r.sliced_prefill_m, r.full_prefill_m)))), tMax = Math.max(...D.slices.map((r) => diff(r.sliced_ttft_p99_ms, r.full_ttft_p99_ms)));
    const pTop = Math.ceil(pMax / 2) * 2 + 1, tTop = Math.ceil(tMax / 10) * 10;
    rowPanels(host, {
      label: `Sliced replays relative to full replays for ${runs.length} runs. Prefill differs by at most ${F1.format(pMax)}%. Sliced p99 TTFT is up to ${F0.format(tMax)}% higher.`,
      rows: runs.map((run) => ({ label: short(run), tipTitle: run, run })), rowH: 34, wideAt: 720,
      panels: [{
        title: 'Prefill tokens, sliced relative to full', domain: [-pTop, pTop], ticks: [-pTop, 0, pTop], baseline: 0, fmt: (v) => (v ? signed(v).replace('.0', '') : '0%'), textW: 14,
        marks: (row) => of(row.run).map((r) => ({ v: diff(r.sliced_prefill_m, r.full_prefill_m), color: COLOR[r.router] })),
        tip: (row) => of(row.run).map((r) => [`${SHORT[r.router]}: ${mInt(r.full_prefill_m)} full, ${mInt(r.sliced_prefill_m)} sliced`, signed(diff(r.sliced_prefill_m, r.full_prefill_m)), COLOR[r.router]]),
      }, {
        title: 'p99 TTFT, sliced relative to full', domain: [0, tTop], ticks: ticks(tTop, 3).filter((v) => v <= tTop), baseline: 0, fmt: (v) => (v ? `+${v}%` : '0%'), textW: 14,
        marks: (row) => of(row.run).map((r) => ({ v: diff(r.sliced_ttft_p99_ms, r.full_ttft_p99_ms), color: COLOR[r.router] })),
        tip: (row) => of(row.run).map((r) => [`${SHORT[r.router]}: ${int(r.full_ttft_p99_ms)} ms full, ${int(r.sliced_ttft_p99_ms)} ms sliced`, signed(diff(r.sliced_ttft_p99_ms, r.full_ttft_p99_ms)), COLOR[r.router]]),
      }],
    });
  }

  // Wrap a label into lines no wider than maxW. Returns the number of lines.
  function wrapText(t, str, maxW, lineH) {
    const words = str.split(' '), x = t.getAttribute('x');
    let line = [], n = 0, span = el('tspan', { x, dy: 0 }, t);
    for (const w of words) {
      line.push(w);
      span.textContent = line.join(' ');
      if (span.getComputedTextLength() > maxW && line.length > 1) {
        line.pop();
        span.textContent = line.join(' ');
        line = [w]; n++;
        span = el('tspan', { x, dy: lineH }, t);
        span.textContent = w;
      }
    }
    return n + 1;
  }

  // Method diagram: the six stages from the public bucket to the tables.
  function pipeline(host, D) {
    const s = D.study[0];
    const nodes = [
      ['Public bucket', `${int(s.trial_dirs)} trial directories in one listing`],
      ['Original-trial selection', `${int(s.originals)} original executions, copies set aside`],
      ['Meter logs', `${int(s.requests)} successful model calls, no prompt text`],
      ['Trace conversion', 'streams, dependencies and prompt blocks per trial'],
      ['Simulator, four routers', `${int(s.replays)} replays of ${int(s.runs)} runs and ${int(s.windows)} windows`],
      ['Aggregates', 'tables, per-unit CSV and the JSON behind this page'],
    ];
    const W = widthOf(host), wide = W >= 860;
    const svg = start(host, W, 10, `Pipeline: ${nodes.map((n) => `${n[0]} (${n[1]})`).join(', then ')}.`);
    const gap = wide ? 26 : 22, bw = wide ? (W - gap * (nodes.length - 1)) / nodes.length : W, pad = 12;
    let y = 0, maxH = 0;
    const boxes = nodes.map(([title, sub], i) => {
      const g = el('g', {}, svg), x = wide ? i * (bw + gap) : 0;
      const rect = el('rect', { x: x + 0.5, width: bw - 1, rx: 4, style: 'fill:var(--paper-2);stroke:var(--axis)' }, g);
      text(g, x + pad, 0, String(i + 1), { class: 'mid' });
      const t = text(g, x + pad + (wide ? 0 : 18), 0, '', { class: 'head' });
      const tl = wide ? wrapText(t, title, bw - 2 * pad, 16) : (t.textContent = title, 1);
      const st = text(g, x + pad + (wide ? 0 : 18), 0, '', {});
      const sl = wrapText(st, sub, bw - 2 * pad - (wide ? 0 : 18), 15);
      const h = (wide ? 30 : 12) + tl * 16 + 6 + sl * 15 + (i === 4 ? 22 : 0) + 8;
      return { g, rect, t, st, x, h, tl, sl };
    });
    maxH = Math.max(...boxes.map((b) => b.h));
    boxes.forEach((b, i) => {
      const h = wide ? maxH : b.h, top = wide ? 0 : y;
      b.rect.setAttribute('y', top + 0.5); b.rect.setAttribute('height', h - 1);
      b.g.querySelector('text').setAttribute('y', top + (wide ? 19 : 24));
      b.t.setAttribute('y', top + (wide ? 40 : 24));
      b.st.setAttribute('y', top + (wide ? 40 : 24) + b.tl * 16 + 4);
      if (i === 4) ROUTERS.forEach((r, k) => el('rect', { x: b.x + pad + (wide ? 0 : 18) + k * 15, y: top + (wide ? 40 : 24) + b.tl * 16 + 4 + b.sl * 15 - 3, width: 10, height: 10, rx: 2, style: `fill:${COLOR[r]}` }, b.g));
      if (i < boxes.length - 1) {
        const stroke = `fill:none;stroke:${INK};stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round`;
        if (wide) { const ax = b.x + bw + 4, ay = maxH / 2; el('path', { d: `M${ax} ${ay}h${gap - 9}m-5 -5l5 5l-5 5`, style: stroke }, svg); }
        else { const ax = 22, ay = top + h + 4; el('path', { d: `M${ax} ${ay}v${gap - 9}m-5 -5l5 5l5 -5`, style: stroke }, svg); }
      }
      y += h + gap;
    });
    resize(svg, W, wide ? maxH : y - gap);
  }

  // Trial directories, original executions and replayable trials on one scale.
  function funnel(host, D) {
    const s = D.study[0], W = widthOf(host);
    const bars = [
      { label: 'Trial directories', total: s.trial_dirs, parts: [['Original executions', s.originals, INK, PAPER], ['Copies of an earlier trial', s.copies, NEUTRAL, INK], ['No identity', s.no_identity, 'var(--neutral-2)', INK]] },
      { label: 'Original executions', total: s.originals, parts: [['Replayable, with at least one successful call', s.replayable_trials, INK, PAPER], ['No successful call', s.originals_without_successful_call, NEUTRAL, INK]] },
    ];
    const x = lin(0, s.trial_dirs, 0, W);
    const svg = start(host, W, 10, `${int(s.trial_dirs)} trial directories: ${int(s.originals)} original executions, ${int(s.copies)} copies of an earlier trial and ${int(s.no_identity)} without an identity. Of the originals, ${int(s.replayable_trials)} made at least one successful call and ${int(s.originals_without_successful_call)} made none.`);
    const pts = [];
    let y0 = 0;
    bars.forEach((b, i) => {
      const head = text(svg, 0, y0 + 13, '', { class: 'lab' });
      el('tspan', { class: 'strong' }, head).textContent = b.label;
      el('tspan', { dx: 8, 'font-family': 'var(--mono)', 'font-size': 11.5 }, head).textContent = int(b.total);
      let at = 0, kx = 0, ky = y0 + 70;
      b.parts.forEach(([name, v, fill, on], k) => {
        const x0 = x(at), w = Math.max(x(v) - (k < b.parts.length - 1 ? 2 : 0), 1.5);
        el('rect', { x: x0, y: y0 + 22, width: w, height: 28, rx: Math.min(3, w / 2), style: `fill:${fill};--i:${k + i * 2}`, class: 'gx' }, svg);
        const t = text(svg, x0 + 8, y0 + 40, int(v), { style: `fill:${on}`, 'font-weight': 500 });
        if (t.getComputedTextLength() + 14 > w) t.remove();
        // Key under the bar: swatch, name and count, wrapping to the next line when it runs out of width.
        const key = text(svg, 0, 0, '', { class: 'lab' });
        key.textContent = `${name} `;
        el('tspan', { 'font-family': 'var(--mono)', 'font-size': 11.5 }, key).textContent = int(v);
        const kw = 15 + key.getComputedTextLength();
        if (kx > 0 && kx + kw > W) { kx = 0; ky += 19; }
        el('rect', { x: kx, y: ky - 9, width: 10, height: 10, rx: 2, style: `fill:${fill}` }, svg);
        key.setAttribute('x', kx + 15); key.setAttribute('y', ky);
        kx += kw + 20;
        pts.push({ box: { x: x0, y: y0 + 20, w: Math.max(w, 10), h: 32 }, title: name, lines: [[b.label.toLowerCase(), int(v)], ['share', pct((100 * v) / b.total)]] });
        at += v;
      });
      y0 = ky + 30;
    });
    resize(svg, W, y0 - 24);
    interact(svg, pts);
  }

  // Runs per day by the date in the run ID, one row per endpoint family.
  function calendar(host, D) {
    const runs = D.runs.filter((r) => r.id_date), fams = D.traffic.map((t) => t.traffic);
    const dayMs = 86400000, d0 = Math.min(...runs.map((r) => Date.parse(r.id_date))), d1 = Math.max(...runs.map((r) => Date.parse(r.id_date)));
    const days = Math.round((d1 - d0) / dayMs) + 1, count = {};
    for (const r of runs) { const k = `${r.traffic}|${r.id_date}`; count[k] = (count[k] || 0) + 1; }
    const max = Math.max(...Object.values(count));
    const W = widthOf(host), wide = W >= 620, lw = wide ? 190 : 0, rowH = 58 + (wide ? 0 : 18), m = { t: 4, b: 24 }, H = fams.length * rowH + m.b;
    const svg = start(host, W, H, `Runs per day by run ID date, ${new Date(d0).toISOString().slice(0, 10)} to ${new Date(d1).toISOString().slice(0, 10)}. ${D.traffic.map((t) => `${t.traffic}: ${t.runs} runs`).join('; ')}.`);
    const slot = (W - lw - 4) / days, bw = Math.min(22, slot - 2), x = (t) => lw + 2 + ((t - d0) / dayMs) * slot + slot / 2;
    const iso = (t) => new Date(t).toISOString().slice(0, 10), pts = [];
    fams.forEach((f, i) => {
      const top = i * rowH + m.t, base = top + rowH - 10, y = lin(0, max, base, base - 40);
      const head = text(svg, 0, wide ? base - 16 : top + 13, '', { class: 'lab' });
      el('tspan', { class: 'strong' }, head).textContent = f;
      text(svg, wide ? 0 : head.getComputedTextLength() + 8, wide ? base - 1 : top + 13, `${D.traffic[i].runs} runs`, {});
      el('line', { x1: lw, x2: W, y1: base, y2: base, class: 'base' }, svg);
      for (let d = 0; d < days; d++) {
        const t = d0 + d * dayMs, n = count[`${f}|${iso(t)}`] || 0;
        if (!n) continue;
        el('path', { d: colPath(x(t) - bw / 2, base, bw, Math.max(base - y(n), 2), 3), style: `fill:${INK};--i:${d}`, class: 'gy' }, svg);
        if (n === max || (bw >= 16 && n >= 10)) text(svg, x(t), y(n) - 5, String(n), { 'text-anchor': 'middle', class: 'mid' });
        pts.push({ x: x(t), y: y(n), box: { x: x(t) - slot / 2, y: base - 46, w: slot, h: 50 }, title: `${f}, ${iso(t)}`, lines: [['runs with this ID date', int(n)]] });
      }
    });
    const every = slot >= 30 ? 2 : slot >= 16 ? 4 : 7;
    for (let d = 0; d < days; d += every) clamp(text(svg, x(d0 + d * dayMs), H - 6, iso(d0 + d * dayMs).slice(5), { 'text-anchor': 'middle' }), 0, W);
    interact(svg, pts, { quiet: true });
  }

  // Tables. Column: [header, cell(row) -> string | {v, cls}, 'l' for left-aligned].
  function table(node, cols, rows) {
    const head = node.querySelector('thead'), body = node.querySelector('tbody');
    head.replaceChildren(); body.replaceChildren();
    const tr = document.createElement('tr');
    for (const [h, , align] of cols) {
      const th = document.createElement('th');
      th.scope = 'col';
      if (align) th.className = 'l';
      th.textContent = h;
      tr.appendChild(th);
    }
    head.appendChild(tr);
    for (const r of rows) {
      const row = document.createElement('tr');
      for (const [, cell, align] of cols) {
        const td = document.createElement('td');
        let v = cell(r), cls = align ? [align === 'wrap' ? 'l wrap' : 'l'] : [];
        if (v && typeof v === 'object') { if (v.cls) cls.push(v.cls); v = v.v; }
        if (cls.length) td.className = cls.join(' ');
        if (align === 'code') { const c = document.createElement('code'); c.textContent = v; td.appendChild(c); td.className = 'l'; }
        else td.textContent = v;
        row.appendChild(td);
      }
      body.appendChild(row);
    }
  }
  const slaCell = (key) => (r) => ({ v: `${r[key]} of ${r.runs}`, cls: r[key] < r.runs ? 'miss' : '' });
  const shareCell = (key) => (r) => ({ v: share(r[key]), cls: r[key] < SLA_SHARE ? 'miss' : '' });
  const byRouter = (a, b) => ORDER.indexOf(a.router) - ORDER.indexOf(b.router);
  const main2 = (D) => D.routers.filter((r) => r.scope === 'all' || r.scope === 'windows');

  const TABLES = {
    routers: (n, D) => table(n, [
      ['Replay', (r) => r.scope_label, 'l'], ['Router', (r) => LABEL[r.router], 'l'],
      ['Prefix reuse', (r) => pct(r.prefix_reuse_pct)], ['Prefill tokens', (r) => bn(r.prefill_tokens_b)],
      ['Meeting SLA', (r) => `${r.units_meeting_sla} of ${r.units}`],
      ['Requests meeting SLA', (r) => pct(r.requests_meeting_sla_pct)],
      ['Mean TTFT', (r) => ms(r.mean_ttft_ms)], ['Median p99 TTFT', (r) => ms(r.median_unit_p99_ttft_ms)],
    ], main2(D)),
    slacounts: (n, D) => table(n, [
      ['Replay', (r) => r.scope_label, 'l'], ['Router', (r) => LABEL[r.router], 'l'],
      ['Meeting SLA', (r) => `${r.units_meeting_sla} of ${r.units}`], ['Missing SLA', (r) => ({ v: int(r.units_missing_sla), cls: r.units_missing_sla ? 'miss' : '' })],
      ['Requests meeting SLA', (r) => pct(r.requests_meeting_sla_pct)],
    ], main2(D)),
    latency: (n, D) => table(n, [
      ['Replay', (r) => r.scope_label, 'l'], ['Router', (r) => LABEL[r.router], 'l'],
      ['Mean TTFT', (r) => ms(r.mean_ttft_ms)], ['Median p99 TTFT', (r) => ms(r.median_unit_p99_ttft_ms)], ['Worst p99 TTFT', (r) => ms(r.worst_unit_p99_ttft_ms)],
    ], main2(D)),
    windows: (n, D) => table(n, [
      ['Endpoint', (r) => r.endpoint, 'l'], ['Start (UTC)', (r) => utc(r.start_unix), 'l'],
      ['Runs merged', (r) => int(r.merged_runs)], ['Trials', (r) => int(r.trials)], ['Peak trials', (r) => int(r.peak_trials)],
      ['Workers', (r) => int(r.workers)],
      ['Round-robin', shareCell('sla_share_rr_pct')], ['KV, defaults', shareCell('sla_share_kv_pct')],
      ['KV, scale 16', shareCell('sla_share_kvp16_pct')], ['Affinity', shareCell('sla_share_aff_pct')],
      ['Default / affinity prefill', (r) => ratio(r.kv_vs_aff_prefill)],
    ], D.windows),
    runs: (n, D) => table(n, [
      ['Run', (r) => r.unit, 'code'], ['Traffic', (r) => r.traffic, 'l'], ['Harness', (r) => r.harness, 'l'],
      ['Trials', (r) => int(r.trials)], ['Peak trials', (r) => int(r.peak_trials)], ['Workers', (r) => int(r.workers)],
      ['Round-robin', shareCell('sla_share_rr_pct')], ['KV, defaults', shareCell('sla_share_kv_pct')],
      ['KV, scale 16', shareCell('sla_share_kvp16_pct')], ['Affinity', shareCell('sla_share_aff_pct')],
      ['Default / affinity prefill', (r) => ratio(r.kv_vs_aff_prefill)],
    ], D.runs),
    traffic: (n, D) => table(n, [
      ['Traffic', (r) => r.traffic, 'l'], ['Runs', (r) => int(r.runs)],
      ['Round-robin', slaCell('sla_rr')], ['KV, defaults', slaCell('sla_kv')], ['KV, scale 16', slaCell('sla_kvp16')], ['Affinity', slaCell('sla_aff')],
      ['Default / affinity prefill', (r) => ratio(r.kv_vs_aff_prefill)], ['Provider cached', (r) => pct(r.provider_cached_pct)],
      ['Affinity prefix reuse', (r) => pct(r.aff_reuse_pct)],
    ], D.traffic),
    harness: (n, D) => table(n, [
      ['Harness', (r) => r.harness, 'l'], ['Runs', (r) => int(r.runs)], ['Requests', (r) => int(r.requests)],
      ['Round-robin', slaCell('sla_rr')], ['KV, defaults', slaCell('sla_kv')], ['KV, scale 16', slaCell('sla_kvp16')], ['Affinity', slaCell('sla_aff')],
      ['Prefill, KV defaults (B)', (r) => bn2(r.prefill_kv_b)], ['Prefill, affinity (B)', (r) => bn2(r.prefill_aff_b)],
      ['Default / affinity prefill', (r) => ratio(r.kv_vs_aff_prefill)],
    ], D.harness),
    poolslices: (n, D) => {
      const out = [];
      for (const [trace, label] of [['hermes_slice', 'Hermes'], ['openclaw_slice', 'OpenClaw']]) {
        for (const w of [...new Set(D.pilot.filter((r) => r.trace === trace).map((r) => r.workers))].sort((a, b) => a - b)) {
          const get = (router) => { const p = D.pilot.find((r) => r.trace === trace && r.workers === w && r.router === router); return p ? pct(p.prefix_reuse_pct) : 'not run'; };
          out.push({ label, w, rr: get('rr'), kv: get('kv'), aff: get('aff') });
        }
      }
      table(n, [['Slice', (r) => r.label, 'l'], ['Workers (GPUs)', (r) => `${r.w} (${2 * r.w})`], ['Round-robin', (r) => r.rr], ['KV router, defaults', (r) => r.kv], ['Session affinity', (r) => r.aff]], out);
    },
    pilot: (n, D) => table(n, [
      ['Workers (GPUs)', (r) => `${r.workers} (${r.gpus})`], ['Router', (r) => LABEL[r.router], 'l'],
      ['Prefix reuse', (r) => pct(r.prefix_reuse_pct)], ['Prefill tokens', (r) => m1(r.prefill_tokens_m)],
      ['Mean TTFT', (r) => ms(r.ttft_mean_ms)], ['p99 TTFT', (r) => ms(r.ttft_p99_ms)], ['p99 ITL', (r) => ms(r.itl_p99_ms)],
      ['Median trial', (r) => min1(r.median_trial_min)],
    ], D.pilot.filter((r) => r.trace === n.dataset.trace).sort((a, b) => a.workers - b.workers || byRouter(a, b))),
    timeline: (n, D) => table(n, [
      ['Bucket start (UTC)', (r) => r.bucket_start.slice(0, 16).replace('T', ' '), 'l'], ['Active trials', (r) => int(r.active_trials)], ['Calls', (r) => int(r.calls)],
      ['Served from cache', (r) => pct(r.provider_cached_pct)], ['Reusable', (r) => pct(r.reusable_pct)],
    ], D.timeline),
    calendar: (n, D) => {
      const fams = D.traffic.map((t) => t.traffic), dates = [...new Set(D.runs.map((r) => r.id_date))].sort();
      const count = (d, f) => D.runs.filter((r) => r.id_date === d && (!f || r.traffic === f)).length;
      table(n, [['Run ID date', (d) => d, 'l'], ...fams.map((f) => [f, (d) => int(count(d, f))]), ['All', (d) => int(count(d))]], dates);
    },
    native: (n, D) => table(n, [
      ['Router', (r) => LABEL[r.router], 'l'], ['Prefix reuse', (r) => pct(r.prefix_reuse_pct)],
      ['Prefill tokens', (r) => mInt(r.prefill_tokens_b * 1000)], ['Relative to affinity', (r) => ratio(r.prefill_vs_affinity)],
      ['Requests meeting SLA', (r) => pct(r.requests_meeting_sla_pct)], ['Mean TTFT', (r) => ms(r.mean_ttft_ms)], ['p99 TTFT', (r) => ms(r.median_unit_p99_ttft_ms)],
    ], D.routers.filter((r) => r.scope === 'deepseek_native')),
    scope: (n, D) => table(n, [
      ['Archive', (r) => ({ v: r.archive, cls: r.archive === 'Total' ? 'total' : '' }), 'l'], ['Trial directories', (r) => int(r.trial_dirs)],
      ['Original executions', (r) => int(r.originals)], ['Copies of an earlier trial', (r) => int(r.copies)], ['No identity', (r) => int(r.no_identity)],
    ], D.scope),
    slices: (n, D) => table(n, [
      ['Run', (r) => r.run, 'code'], ['Router', (r) => LABEL[r.router], 'l'],
      ['Prefix reuse, full / sliced', (r) => `${pct(r.full_reuse_pct)} / ${pct(r.sliced_reuse_pct)}`],
      ['Prefill, full / sliced', (r) => `${mInt(r.full_prefill_m)} / ${mInt(r.sliced_prefill_m)}`],
      ['Requests meeting SLA, full / sliced', (r) => `${pct(r.full_sla_pct)} / ${pct(r.sliced_sla_pct)}`],
      ['p99 TTFT, full / sliced', (r) => `${int(r.full_ttft_p99_ms)} / ${int(r.sliced_ttft_p99_ms)} ms`],
    ], D.slices),
  };

  // Figure titles state the takeaway, with every number taken from the data.
  const TITLES = {
    'hero-ratio': (D) => ratio(routerRows(D, 'all')[1].prefill_vs_affinity),
    hero: (D) => `Prompt tokens recomputed across all ${routerRows(D, 'all')[0].units} runs, by router`,
    'hero-note': (D) => `Each block is the session-affinity total of ${bn(routerRows(D, 'all')[3].prefill_tokens_b)} tokens, so the blocks in a row count that router's multiple of it.`,
    bars: (D) => { const a = routerRows(D, 'all'), w = routerRows(D, 'windows'); return `The default KV router recomputes ${ratio(a[1].prefill_vs_affinity)} what session affinity does on single runs, and ${ratio(w[1].prefill_vs_affinity)} when concurrent runs are merged`; },
    units: (D) => { const a = routerRows(D, 'all'), w = routerRows(D, 'windows'); return `The default KV router misses the SLA on ${a[1].units_missing_sla} of ${a[1].units} runs and ${w[1].units_missing_sla} of ${w[1].units} endpoint windows. ${a[3].units_missing_sla || w[3].units_missing_sla ? `Session affinity misses it on ${a[3].units_missing_sla} of the runs and ${w[3].units_missing_sla} of the windows` : 'Session affinity meets it on every run and window'}`; },
    latency: (D) => { const a = routerRows(D, 'all'), w = routerRows(D, 'windows'); return `The middle run's p99 time to first token is ${ms(a[1].median_unit_p99_ttft_ms)} with the default KV router and ${ms(a[3].median_unit_p99_ttft_ms)} with session affinity. In the endpoint windows it is ${ms(w[1].median_unit_p99_ttft_ms)} against ${ms(w[3].median_unit_p99_ttft_ms)}`; },
    heat: (D) => { const c = (r) => D.windows.filter((w) => w[`sla_${r}`] === 'meets').length, n = D.windows.length; return `With the default KV router, ${c('kv')} of ${n} endpoint windows keeps 99% of its requests inside the SLA. With prefill_load_scale 16 or session affinity, all ${c('aff')} do`; },
    ratio: (D) => { const s = routerRows(D, 'all')[1]; return `In the median run the default KV router prefills ${ratio(s.prefill_vs_affinity_run_median)} what affinity does, and in the 90th-percentile run ${ratio(s.prefill_vs_affinity_run_p90)}`; },
    scatter: (D) => {
      const med = (a) => { const s = a.slice().sort((x, y) => x - y), h = s.length >> 1; return s.length % 2 ? s[h] : (s[h - 1] + s[h]) / 2; };
      const cut = 25, lo = D.runs.filter((r) => r.peak_trials < cut), hi = D.runs.filter((r) => r.peak_trials >= cut);
      return `The ${lo.length} runs that peak below ${cut} concurrent trials have a median gap of ${ratio(med(lo.map((r) => r.kv_vs_aff_prefill)))}. The ${hi.length} runs at ${cut} or more have a median gap of ${ratio(med(hi.map((r) => r.kv_vs_aff_prefill)))}`;
    },
    traffic: (D) => { const v = D.traffic.map((t) => t.kv_vs_aff_prefill), f = D.traffic.reduce((a, b) => (b.provider_cached_pct < a.provider_cached_pct ? b : a)); return `On every traffic source the default KV router prefills ${F1.format(Math.min(...v))}-${ratio(Math.max(...v))} what affinity does. The ${f.traffic} endpoint served ${pct(f.provider_cached_pct)} of prompt tokens from cache where simulated affinity reuses ${pct(f.aff_reuse_pct)}`; },
    harness: (D) => `${D.harness.filter((h) => h.sla_kv < h.runs).length} of ${D.harness.length} harness versions have runs that miss the SLA with the default KV router. ${((n) => (n ? `With session affinity, ${n} ${n === 1 ? 'does' : 'do'}` : 'With session affinity, none does'))(D.harness.filter((h) => h.sla_aff < h.runs).length)}`,
    pilotfull: (D) => { const h = D.pilot.filter((r) => r.trace === 'hermes_run'), a = h.filter((r) => r.router === 'aff').sort((x, y) => x.gpus - y.gpus)[0], k = h.filter((r) => r.router === 'kv').sort((x, y) => y.gpus - x.gpus)[0]; return `On the Hermes run, session affinity on ${a.gpus} GPUs reaches a p99 TTFT of ${ms(a.ttft_p99_ms)}. The default KV router on ${k.gpus} GPUs reaches ${ms(k.ttft_p99_ms)}`; },
    timeline: (D) => `The flint endpoint's cached share fell to ${pct(Math.min(...D.timeline.map((r) => r.provider_cached_pct)))} while ${pct(Math.min(...D.timeline.map((r) => r.reusable_pct)))} or more of the prompt stayed reusable`,
    native: (D) => { const k = D.native.find((r) => r.router === 'kv'); return `On the native DeepSeek-V4.1-Flash target the default KV router prefills ${ratio(k.native_prefill_vs_affinity)} what affinity does, and ${ratio(k.target_prefill_vs_affinity)} on the GLM-5.3-Flash target`; },
    'native-d': (D) => { const k = D.native[0]; return `The same DeepSeek run replayed on simulated DeepSeek-V4.1-Flash (${k.native_gpus} GPUs) and on the GLM-5.3-Flash target used everywhere else on this page (${k.target_gpus} GPUs). Prefill tokens in millions, and the 99th-percentile TTFT with the 2 s bound marked.`; },
    slices: (D) => { const d = (a, b) => 100 * (a / b - 1); return `Sliced and full replays agree within ${F1.format(Math.max(...D.slices.map((r) => Math.abs(d(r.sliced_prefill_m, r.full_prefill_m)))))}% on prefill. Sliced p99 TTFT runs up to ${F0.format(Math.max(...D.slices.map((r) => d(r.sliced_ttft_p99_ms, r.full_ttft_p99_ms))))}% higher`; },
    calendar: (D) => { const dates = [...new Set(D.runs.map((r) => r.id_date))].sort(), last = dates.slice(-5), n = D.runs.filter((r) => last.includes(r.id_date)).length; return `${n} of the ${D.runs.length} runs carry IDs dated ${last[0]} to ${last[last.length - 1]}`; },
    funnel: (D) => { const s = D.study[0]; return `${int(s.originals)} of ${int(s.trial_dirs)} trial directories are original executions, and ${int(s.replayable_trials)} of those made a successful call`; },
  };
  const CHARTS = { hero, routing, bars, units, latency, heat, ratio: ratioDist, scatter, traffic, harness, pool, pilotfull: pilotFull, timeline, native, slices, pipeline, funnel, calendar };

  function fail(host) {
    host.replaceChildren(html('p', 'failed', 'The data for this figure did not load. The tables are in results/ in the repository.'));
  }
  function draw(host, D) {
    try { CHARTS[host.dataset.chart](host, D); } catch (err) { console.error(host.dataset.chart, err); fail(host); }
  }

  // Section navigation: mark the section in view, and open a table when its anchor is the target.
  function wayfinding() {
    const links = [...document.querySelectorAll('.toc a')];
    const targets = links.map((a) => document.getElementById(a.getAttribute('href').slice(1)));
    const update = () => {
      let cur = -1;
      targets.forEach((t, i) => { if (t && t.getBoundingClientRect().top <= 120) cur = i; });
      links.forEach((a, i) => { if (i === cur) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current'); });
      const active = links[cur], bar = document.querySelector('.toc');
      if (active && bar.scrollWidth > bar.clientWidth) {
        const left = active.offsetLeft - bar.offsetLeft;
        if (left < bar.scrollLeft || left + active.offsetWidth > bar.scrollLeft + bar.clientWidth - 24) bar.scrollLeft = Math.max(0, left - 16);
      }
    };
    let queued = false;
    window.addEventListener('scroll', () => { if (!queued) { queued = true; requestAnimationFrame(() => { queued = false; update(); }); } }, { passive: true });
    update();
    const openTarget = () => {
      const t = location.hash && document.getElementById(location.hash.slice(1));
      const d = t && (t.tagName === 'DETAILS' ? t : t.closest('details'));
      if (d) { d.open = true; t.scrollIntoView(); }
    };
    window.addEventListener('hashchange', openTarget);
    openTarget();
  }

  async function main() {
    document.body.appendChild(tipEl);
    wayfinding();
    const D = {}, hosts = [...document.querySelectorAll('[data-chart]')];
    try {
      await Promise.all(DATASETS.map(async (name) => {
        const res = await fetch(`data/${name}.json`);
        if (!res.ok) throw new Error(`data/${name}.json: HTTP ${res.status}`);
        D[name] = (await res.json()).rows;
      }));
    } catch (err) {
      console.error(err);
      hosts.forEach(fail);
      return;
    }
    document.querySelectorAll('[data-title], [data-fill]').forEach((n) => {
      try { n.textContent = TITLES[n.dataset.title || n.dataset.fill](D); } catch (err) { console.error(err); }
    });
    document.querySelectorAll('table[data-table]').forEach((n) => TABLES[n.dataset.table](n, D));
    hosts.forEach((host) => draw(host, D));
    // Redraw a chart when its container changes width, and once the web fonts have loaded.
    const widths = new Map();
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const host = entry.target, w = Math.floor(entry.contentRect.width);
        if (w === widths.get(host)) continue;
        widths.set(host, w);
        if (w > 0) draw(host, D);
      }
    });
    hosts.forEach((host) => { widths.set(host, Math.floor(host.clientWidth)); observer.observe(host); });
    if (document.fonts) {
      let timer = 0;
      const redraw = () => { clearTimeout(timer); timer = setTimeout(() => hosts.forEach((host) => draw(host, D)), 60); };
      document.fonts.ready.then(redraw);
      document.fonts.addEventListener('loadingdone', redraw);
    }
    // Figures draw in once, the first time they come into view.
    const seen = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const host = entry.target;
        seen.unobserve(host);
        host.classList.add('in');
        setTimeout(() => host.classList.add('done'), 1600);
      }
    }, { threshold: 0.2 });
    hosts.forEach((host) => seen.observe(host));
  }
  main();
})();
