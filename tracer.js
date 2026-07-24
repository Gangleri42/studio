"use strict";
// SeedHammer Studio — raster image tracer.
//
// Turns a dropped raster (logo, signature, line art) into engravable strokes.
// The engraver is a single-stroke centerline machine with no fill, so two
// modes are offered:
//   outline    — marching-squares boundary of the dark region (hollow shapes)
//   centerline — Zhang-Suen thinning to a 1px skeleton, walked into strokes
//                (the aesthetically correct single-stroke match)
// Output is a segs array (M/L runs) in image pixel space; the caller scales
// and centers it into a scene object. Everything is pure in-browser canvas
// work, no toolchain, no network.
window.Tracer = (function () {
  const MAXDIM = 360;   // cap the working raster; enough detail, bounded cost

  function loadImageData(file) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        let w = img.width, h = img.height; const s = Math.min(1, MAXDIM / Math.max(w, h));
        w = Math.max(1, Math.round(w * s)); h = Math.max(1, Math.round(h * s));
        const c = document.createElement("canvas"); c.width = w; c.height = h;
        const cx = c.getContext("2d"); cx.fillStyle = "#fff"; cx.fillRect(0, 0, w, h); cx.drawImage(img, 0, 0, w, h);
        resolve(cx.getImageData(0, 0, w, h));
      };
      img.onerror = () => reject("bad image");
      img.src = URL.createObjectURL(file);
    });
  }
  // luma + Otsu threshold -> binary (1 = ink/dark)
  function binarize(id) {
    const { width: w, height: h, data } = id, gray = new Uint8Array(w * h), hist = new Array(256).fill(0);
    for (let i = 0, j = 0; i < data.length; i += 4, j++) {
      const a = data[i + 3] / 255;
      const l = (0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]) * a + 255 * (1 - a);
      gray[j] = l | 0; hist[gray[j]]++;
    }
    const total = w * h; let sum = 0; for (let t = 0; t < 256; t++) sum += t * hist[t];
    let sumB = 0, wB = 0, max = 0, thr = 128;
    for (let t = 0; t < 256; t++) { wB += hist[t]; if (!wB) continue; const wF = total - wB; if (!wF) break; sumB += t * hist[t]; const mB = sumB / wB, mF = (sum - sumB) / wF, between = wB * wF * (mB - mF) ** 2; if (between > max) { max = between; thr = t; } }
    const bin = new Uint8Array(w * h); for (let i = 0; i < bin.length; i++) bin[i] = gray[i] < thr ? 1 : 0;
    return { bin, w, h };
  }

  // ---- outline: marching squares over the binary field -------------------
  function outline(b, eps) {
    const { bin, w, h } = b, W = w + 1, H = h + 1;
    const get = (x, y) => (x < 0 || y < 0 || x >= w || y >= h) ? 0 : bin[y * w + x];
    // edge-following on the cell grid; visited edges tracked to avoid repeats
    const seen = new Set(), loops = [];
    const key = (x, y, d) => x + "," + y + "," + d;
    // For each boundary cell, trace the contour with Moore-neighbour walk.
    // Simpler robust route: for every pixel that is ink with a non-ink 4-neighbour,
    // walk the boundary using a square-tracing (Moore) algorithm.
    const visited = new Uint8Array(w * h);
    const dirs = [[1, 0], [0, 1], [-1, 0], [0, -1]];
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      if (!get(x, y) || visited[y * w + x]) continue;
      if (get(x - 1, y) && get(x + 1, y) && get(x, y - 1) && get(x, y + 1)) continue; // interior
      const loop = traceContour(get, x, y, w, h, visited);
      if (loop && loop.length >= 4) loops.push(loop);
    }
    const segs = [];
    for (let lp of loops) { lp = rdp(lp, eps); if (lp.length >= 2) { segs.push({ op: "M", p: [lp[0]] }); for (let i = 1; i < lp.length; i++) segs.push({ op: "L", p: [lp[i]] }); segs.push({ op: "L", p: [lp[0]] }); } }
    return segs;
  }
  // Moore-neighbour boundary tracing from a start ink pixel.
  function traceContour(get, sx, sy, w, h, visited) {
    const loop = []; const N8 = [[1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0], [-1, -1], [0, -1], [1, -1]];
    let cx = sx, cy = sy, bDir = 6; // came-from direction index
    let count = 0, max = w * h * 4;
    do {
      loop.push([cx + 0.5, cy + 0.5]); visited[cy * w + cx] = 1;
      let found = false, start = (bDir + 6) % 8;
      for (let k = 0; k < 8; k++) { const d = (start + k) % 8, nx = cx + N8[d][0], ny = cy + N8[d][1];
        if (nx >= 0 && ny >= 0 && nx < w && ny < h && get(nx, ny)) { bDir = (d + 4) % 8; cx = nx; cy = ny; found = true; break; } }
      if (!found) break;
      if (++count > max) break;
    } while (!(cx === sx && cy === sy) || loop.length < 3);
    return loop;
  }

  // ---- centerline: Zhang-Suen thinning + skeleton walk -------------------
  function centerline(b, eps) {
    const { w, h } = b; let bin = b.bin.slice();
    const at = (x, y) => (x < 0 || y < 0 || x >= w || y >= h) ? 0 : bin[y * w + x];
    let changed = true, guard = 0;
    while (changed && guard++ < 200) {
      changed = false;
      for (let step = 0; step < 2; step++) {
        const del = [];
        for (let y = 1; y < h - 1; y++) for (let x = 1; x < w - 1; x++) {
          if (!bin[y * w + x]) continue;
          const p = [at(x, y - 1), at(x + 1, y - 1), at(x + 1, y), at(x + 1, y + 1), at(x, y + 1), at(x - 1, y + 1), at(x - 1, y), at(x - 1, y - 1)];
          let B = 0, A = 0; for (let i = 0; i < 8; i++) { B += p[i]; if (!p[i] && p[(i + 1) % 8]) A++; }
          if (B < 2 || B > 6 || A !== 1) continue;
          const c1 = step === 0 ? p[0] * p[2] * p[4] : p[0] * p[2] * p[6];
          const c2 = step === 0 ? p[2] * p[4] * p[6] : p[0] * p[4] * p[6];
          if (c1 === 0 && c2 === 0) del.push(y * w + x);
        }
        if (del.length) { changed = true; for (const idx of del) bin[idx] = 0; }
      }
    }
    // walk the skeleton: classify by 8-neighbour count, trace edges endpoint->junction
    const nb = (x, y) => { let n = 0; for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) if ((dx || dy) && at(x + dx, y + dy)) n++; return n; };
    const N8 = [[1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0], [-1, -1], [0, -1], [1, -1]];
    const used = new Uint8Array(w * h), segs = [];
    const nodes = [];
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (bin[y * w + x]) { const n = nb(x, y); if (n === 1 || n >= 3) nodes.push([x, y]); }
    const walk = (x, y) => {
      const line = [[x, y]]; let px = x, py = y, first = true;
      while (true) {
        let nx = -1, ny = -1;
        for (const [dx, dy] of N8) { const ax = px + dx, ay = py + dy; if (at(ax, ay) && !used[ay * w + ax]) { nx = ax; ny = ay; break; } }
        if (nx < 0) break;
        used[ny * w + nx] = 1; line.push([nx, ny]);
        const deg = nb(nx, ny); px = nx; py = ny;
        if (deg !== 2) break; // stop at junction/endpoint
      }
      return line;
    };
    for (const [x, y] of nodes) { used[y * w + x] = 1; }
    for (const [x, y] of nodes) for (const [dx, dy] of N8) { const ax = x + dx, ay = y + dy; if (at(ax, ay) && !used[ay * w + ax]) { used[ay * w + ax] = 1; const line = [[x, y], [ax, ay]].concat(walk(ax, ay).slice(1)); pushLine(segs, line, eps); } }
    // any remaining unused ink = closed loops with no endpoint
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (bin[y * w + x] && !used[y * w + x]) { used[y * w + x] = 1; const line = [[x, y]].concat(walk(x, y).slice(1)); pushLine(segs, line, eps); }
    return segs;
  }
  function pushLine(segs, line, eps) { if (line.length < 2) return; let l = rdp(line.map(p => [p[0] + 0.5, p[1] + 0.5]), eps); if (l.length < 2) return; segs.push({ op: "M", p: [l[0]] }); for (let i = 1; i < l.length; i++) segs.push({ op: "L", p: [l[i]] }); }

  // ---- Ramer-Douglas-Peucker ---------------------------------------------
  function rdp(points, eps) {
    if (points.length < 3) return points;
    let dmax = 0, idx = 0; const a = points[0], b = points[points.length - 1];
    for (let i = 1; i < points.length - 1; i++) { const d = segDist(points[i], a, b); if (d > dmax) { dmax = d; idx = i; } }
    if (dmax > eps) { const l = rdp(points.slice(0, idx + 1), eps), r = rdp(points.slice(idx), eps); return l.slice(0, -1).concat(r); }
    return [a, b];
  }
  function segDist(p, a, b) { const dx = b[0] - a[0], dy = b[1] - a[1], L = dx * dx + dy * dy; if (!L) return Math.hypot(p[0] - a[0], p[1] - a[1]); let t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L; t = Math.max(0, Math.min(1, t)); return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy)); }

  async function trace(file, opts) {
    const id = await loadImageData(file), b = binarize(id);
    const eps = 0.8 + 3 * (1 - (opts && opts.detail != null ? opts.detail : 1));
    const segs = (opts && opts.mode === "outline") ? outline(b, eps) : centerline(b, eps);
    if (!segs.length) throw "no strokes found";
    return segs;
  }
  return { trace };
})();
