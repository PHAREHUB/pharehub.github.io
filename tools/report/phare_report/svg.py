"""Small inline-SVG charts. Colors come from CSS classes so both themes work."""

from html import escape

BAR_MAX = 24  # px, mark width cap
RADIUS = 4


def _column(x, y, w, h, cls, tip):
    """Column with a rounded top and a square base."""
    if h <= 0:
        return ""
    r = min(RADIUS, h, w / 2)
    d = (f"M{x:.1f},{y + h:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
         f"H{x + w - r:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} V{y + h:.1f} Z")
    t = escape(tip)
    return f'<path class="{cls}" d="{d}" data-tip="{t}"><title>{t}</title></path>'


def columns(values, labels, tips, height=72, width=210, cls="m-accent"):
    """Single-series column chart: one column per value, the maximum labeled."""
    n = len(values)
    top, bottom = 14, 16
    plot_h = height - top - bottom
    slot = width / n
    w = min(BAR_MAX, slot * 0.62)
    vmax = max(max(values), 1)
    imax = values.index(max(values)) if any(values) else None
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" preserveAspectRatio="xMidYMid meet">',
           f'<line class="axis" x1="0" x2="{width}" y1="{top + plot_h + .5}" y2="{top + plot_h + .5}"/>']
    for i, (v, lab, tip) in enumerate(zip(values, labels, tips)):
        cx = slot * (i + .5)
        h = plot_h * v / vmax
        out.append(_column(cx - w / 2, top + plot_h - h, w, h, cls, tip))
        # invisible full-height hit target, larger than the mark
        out.append(f'<rect class="hit" x="{slot * i:.1f}" y="0" width="{slot:.1f}" height="{height}" '
                   f'data-tip="{escape(tip)}"/>')
        if n <= 31 and (n <= 8 or i % 7 == 0):
            out.append(f'<text class="tick" x="{cx:.1f}" y="{height - 3}" text-anchor="middle">{escape(lab)}</text>')
        if i == imax:
            out.append(f'<text class="val" x="{cx:.1f}" y="{top + plot_h - h - 4:.1f}" text-anchor="middle">{v}</text>')
    out.append("</svg>")
    return "".join(out)


def stacked_columns(series, labels, tips, height=150, width=1000):
    """Columns stacked from the baseline; `series` = [(css_class, values), ...] bottom to top."""
    n = len(labels)
    top, bottom = 16, 18
    plot_h = height - top - bottom
    slot = width / n
    w = min(BAR_MAX * 1.5, slot * 0.62)
    totals = [sum(vals[i] for _, vals in series) for i in range(n)]
    vmax = max(max(totals), 1)
    imax = totals.index(max(totals)) if any(totals) else None
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" preserveAspectRatio="xMidYMid meet">',
           f'<line class="axis" x1="0" x2="{width}" y1="{top + plot_h + .5}" y2="{top + plot_h + .5}"/>']
    for i in range(n):
        cx, base = slot * (i + .5), top + plot_h
        nonzero = [(cls, vals[i]) for cls, vals in series if vals[i]]
        for k, (cls, v) in enumerate(nonzero):
            h = plot_h * v / vmax
            gap = 2 if k else 0  # surface gap between stacked segments
            if k == len(nonzero) - 1:
                out.append(_column(cx - w / 2, base - h, w, h - gap, cls, tips[i]))
            else:
                out.append(f'<rect class="{cls}" x="{cx - w / 2:.1f}" y="{base - h:.1f}" width="{w:.1f}" '
                           f'height="{max(h - gap, 0):.1f}" data-tip="{escape(tips[i])}"/>')
            base -= h
        out.append(f'<rect class="hit" x="{slot * i:.1f}" y="0" width="{slot:.1f}" height="{height}" '
                   f'data-tip="{escape(tips[i])}"/>')
        out.append(f'<text class="tick" x="{cx:.1f}" y="{height - 4}" text-anchor="middle">{escape(labels[i])}</text>')
        if i == imax:
            out.append(f'<text class="val" x="{cx:.1f}" y="{top + plot_h * (1 - totals[i] / vmax) - 5:.1f}" '
                       f'text-anchor="middle">{totals[i]}</text>')
    out.append("</svg>")
    return "".join(out)


def hbar(value, vmax, cls="m-accent", width=120, height=10):
    """A thin horizontal bar for table cells, rounded at the data end."""
    w = 0 if vmax <= 0 else width * value / vmax
    r = min(RADIUS, height / 2, w)
    if w <= 0:
        return f'<svg class="hbar" viewBox="0 0 {width} {height}" width="{width}" height="{height}"></svg>'
    d = (f"M0,0 H{w - r:.1f} Q{w:.1f},0 {w:.1f},{r:.1f} V{height - r:.1f} "
         f"Q{w:.1f},{height} {w - r:.1f},{height} H0 Z")
    return (f'<svg class="hbar" viewBox="0 0 {width} {height}" width="{width}" height="{height}" aria-hidden="true">'
            f'<path class="{cls}" d="{d}"/></svg>')


def sparkline(values, width=120, height=30):
    """Trend line, no text: a wash under the line and a dot on the latest value."""
    n, vmax = len(values), max(max(values), 1)
    pad = 4
    xs = [pad + (width - 2 * pad) * i / (n - 1) for i in range(n)]
    ys = [height - pad - (height - 2 * pad) * v / vmax for v in values]
    line = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(zip(xs, ys)))
    area = f"{line} L{xs[-1]:.1f},{height - pad} L{xs[0]:.1f},{height - pad} Z"
    return (f'<svg class="spark" viewBox="0 0 {width} {height}" aria-hidden="true">'
            f'<path class="spark-area" d="{area}"/><path class="spark-line" d="{line}"/>'
            f'<circle class="spark-dot" cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="3.5"/></svg>')
