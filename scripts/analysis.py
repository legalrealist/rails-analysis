#!/usr/bin/env python3
"""Analysis and charts for the AI court orders dataset (reads from JSON)."""

import json
import os
from collections import Counter, defaultdict
import plotly.graph_objects as go

INPUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'explorer_data.json')
CHARTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'charts')
ANALYSIS_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'analysis')

os.makedirs(CHARTS_DIR, exist_ok=True)
os.makedirs(ANALYSIS_DIR, exist_ok=True)

COLORS = {
    'blue': '#2563eb',
    'red': '#dc2626',
    'green': '#16a34a',
    'orange': '#ea580c',
    'purple': '#9333ea',
    'gray': '#6b7280',
    'lightblue': '#93c5fd',
    'lightred': '#fca5a5',
    'teal': '#0d9488',
    'amber': '#d97706',
}

ORDER_TYPES = ('Standing Order', 'Local Rules', 'Administrative Order', 'Practice Direction')

SANCTION_TYPE_LABELS = {
    'monetary': 'Monetary',
    'dismissal': 'Dismissal',
    'striking': 'Striking',
    'bar_referral': 'Bar Referral',
    'cle': 'CLE Required',
    'show_cause': 'Show Cause',
    'admonishment': 'Admonishment',
    'contempt': 'Contempt',
}


def load_data():
    with open(INPUT, encoding='utf-8') as f:
        return json.load(f)


def is_order(r):
    return r['type'] in ORDER_TYPES


def is_opinion(r):
    return r['type'] == 'Judicial Opinion'


def is_sanction(r):
    return r.get('consequence', '') in ('sanctions_party', 'sanctions_attorney')


def is_warning(r):
    return r.get('consequence', '') == 'warning'


def orders_vs_opinions_by_month(rows):
    orders_by_month = Counter()
    opinions_by_month = Counter()

    for r in rows:
        ym = r.get('date', '')
        if not ym:
            continue
        if is_order(r):
            orders_by_month[ym] += 1
        elif is_opinion(r):
            opinions_by_month[ym] += 1

    all_months = sorted(set(list(orders_by_month.keys()) + list(opinions_by_month.keys())))

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=all_months,
        y=[orders_by_month.get(m, 0) for m in all_months],
        name='Standing Orders / Rules',
        marker_color=COLORS['blue'],
    ))
    fig.add_trace(go.Bar(
        x=all_months,
        y=[opinions_by_month.get(m, 0) for m in all_months],
        name='Judicial Opinions (sanctions/warnings)',
        marker_color=COLORS['red'],
    ))
    fig.update_layout(
        title='AI Court Activity by Month: Orders vs. Enforcement',
        xaxis_title='Month',
        yaxis_title='Count',
        barmode='group',
        template='plotly_white',
        legend=dict(x=0.01, y=0.99),
        height=500,
    )
    fig.write_html(os.path.join(CHARTS_DIR, 'orders_vs_opinions_monthly.html'))
    return all_months, orders_by_month, opinions_by_month


def cumulative_growth(rows):
    orders_by_month = Counter()
    opinions_by_month = Counter()

    for r in rows:
        ym = r.get('date', '')
        if not ym:
            continue
        if is_order(r):
            orders_by_month[ym] += 1
        elif is_opinion(r):
            opinions_by_month[ym] += 1

    all_months = sorted(set(list(orders_by_month.keys()) + list(opinions_by_month.keys())))

    cum_orders, cum_opinions = [], []
    total_o, total_p = 0, 0
    for m in all_months:
        total_o += orders_by_month.get(m, 0)
        total_p += opinions_by_month.get(m, 0)
        cum_orders.append(total_o)
        cum_opinions.append(total_p)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=all_months, y=cum_orders,
        name='Cumulative Orders/Rules',
        line=dict(color=COLORS['blue'], width=3),
        fill='tozeroy', fillcolor='rgba(37,99,235,0.1)',
    ))
    fig.add_trace(go.Scatter(
        x=all_months, y=cum_opinions,
        name='Cumulative Opinions',
        line=dict(color=COLORS['red'], width=3),
        fill='tozeroy', fillcolor='rgba(220,38,38,0.1)',
    ))
    fig.update_layout(
        title='Cumulative Growth: Standing Orders vs. Judicial Opinions',
        xaxis_title='Month',
        yaxis_title='Cumulative Count',
        template='plotly_white',
        legend=dict(x=0.01, y=0.99),
        height=500,
    )
    fig.write_html(os.path.join(CHARTS_DIR, 'cumulative_growth.html'))


def by_state(rows):
    state_orders = Counter()
    state_opinions = Counter()

    for r in rows:
        st = r.get('state', '')
        if not st or st == '-':
            continue
        if is_order(r):
            state_orders[st] += 1
        elif is_opinion(r):
            state_opinions[st] += 1

    all_states = set(list(state_orders.keys()) + list(state_opinions.keys()))
    state_total = {s: state_orders.get(s, 0) + state_opinions.get(s, 0) for s in all_states}
    top = sorted(state_total.items(), key=lambda x: x[1], reverse=True)[:20]
    states = [s for s, _ in reversed(top)]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=states,
        x=[state_orders.get(s, 0) for s in states],
        name='Orders/Rules',
        orientation='h',
        marker_color=COLORS['blue'],
    ))
    fig.add_trace(go.Bar(
        y=states,
        x=[state_opinions.get(s, 0) for s in states],
        name='Opinions',
        orientation='h',
        marker_color=COLORS['red'],
    ))
    fig.update_layout(
        title='AI Court Activity by State (Top 20)',
        xaxis_title='Count',
        barmode='stack',
        template='plotly_white',
        height=600,
        legend=dict(x=0.7, y=0.05),
    )
    fig.write_html(os.path.join(CHARTS_DIR, 'by_state.html'))


def document_type_breakdown(rows):
    dt = Counter(r['type'] for r in rows if r.get('type'))

    fig = go.Figure(go.Pie(
        labels=list(dt.keys()),
        values=list(dt.values()),
        marker_colors=[COLORS['red'], COLORS['blue'], COLORS['green'],
                       COLORS['orange'], COLORS['purple']],
        textinfo='label+value+percent',
        hole=0.3,
    ))
    fig.update_layout(
        title='Document Type Breakdown',
        template='plotly_white',
        height=500,
    )
    fig.write_html(os.path.join(CHARTS_DIR, 'document_types.html'))


def requirements_heatmap(rows):
    orders = [r for r in rows if is_order(r)]

    req_cols = [
        ('Disclose AI use', 'disclose'),
        ('Disclose tool used', 'tool'),
        ('Disclose how used', 'how'),
        ('ID sections drafted', 'sections'),
        ('Verify accuracy process', 'verify'),
        ('Certify accuracy/non-use\n(each filing)', 'certify_all'),
        ('Certify accuracy\n(if AI used)', 'certify_if_ai'),
        ('Certify no unauthorized\ndisclosure', 'evidence'),
        ('Retain AI prompts', 'prompts'),
        ('Protect proprietary info', 'proprietary'),
        ('Just a warning', 'warning'),
        ('Prohibits AI', 'prohibited'),
        ('References FRCP 11+', 'rules'),
    ]

    labels = [l for l, _ in req_cols]
    counts = []
    for label, key in req_cols:
        c = sum(1 for r in orders if r.get('reqs', {}).get(key))
        counts.append(c)

    pcts = [100 * c / len(orders) if orders else 0 for c in counts]

    fig = go.Figure(go.Bar(
        x=pcts,
        y=labels,
        orientation='h',
        marker_color=COLORS['blue'],
        text=[f'{c} ({p:.0f}%)' for c, p in zip(counts, pcts)],
        textposition='auto',
    ))
    fig.update_layout(
        title=f'Requirements in Standing Orders & Rules (n={len(orders)})',
        xaxis_title='% of Orders',
        template='plotly_white',
        height=550,
        margin=dict(l=200),
    )
    fig.write_html(os.path.join(CHARTS_DIR, 'requirements_breakdown.html'))


def enforcement_analysis(rows):
    judges = defaultdict(lambda: {'orders': [], 'opinions': []})
    for r in rows:
        j = r.get('judge', '').lower().strip()
        court = r.get('court', '').strip()
        if not j:
            continue
        key = (j, court)
        if is_order(r):
            judges[key]['orders'].append(r)
        elif is_opinion(r):
            judges[key]['opinions'].append(r)

    districts_with_orders = set()
    for (j, court), v in judges.items():
        if v['orders'] and court:
            districts_with_orders.add(court)

    categories = {'Same judge': {'sanctions': 0, 'warning': 0, 'other': 0},
                  'Same district': {'sanctions': 0, 'warning': 0, 'other': 0},
                  'No order': {'sanctions': 0, 'warning': 0, 'other': 0}}

    for (j, court), v in judges.items():
        for op in v['opinions']:
            if v['orders']:
                cat = 'Same judge'
            elif court in districts_with_orders:
                cat = 'Same district'
            else:
                cat = 'No order'

            if is_sanction(op):
                categories[cat]['sanctions'] += 1
            elif is_warning(op):
                categories[cat]['warning'] += 1
            else:
                categories[cat]['other'] += 1

    cats = ['Same judge', 'Same district', 'No order']
    fig = go.Figure()
    fig.add_trace(go.Bar(name='Sanctions', x=cats,
                         y=[categories[c]['sanctions'] for c in cats],
                         marker_color=COLORS['red']))
    fig.add_trace(go.Bar(name='Warnings', x=cats,
                         y=[categories[c]['warning'] for c in cats],
                         marker_color=COLORS['orange']))
    fig.add_trace(go.Bar(name='Other', x=cats,
                         y=[categories[c]['other'] for c in cats],
                         marker_color=COLORS['gray']))
    fig.update_layout(
        title='Enforcement Outcomes by Standing Order Relationship',
        yaxis_title='Count',
        barmode='stack',
        template='plotly_white',
        height=500,
    )
    fig.write_html(os.path.join(CHARTS_DIR, 'enforcement_by_order.html'))
    return categories


def sanctions_timeline(rows):
    sanctions_by_month = Counter()
    warnings_by_month = Counter()

    for r in rows:
        if not is_opinion(r):
            continue
        ym = r.get('date', '')
        if not ym:
            continue
        if is_sanction(r):
            sanctions_by_month[ym] += 1
        elif is_warning(r):
            warnings_by_month[ym] += 1

    all_months = sorted(set(list(sanctions_by_month.keys()) + list(warnings_by_month.keys())))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=all_months,
        y=[sanctions_by_month.get(m, 0) for m in all_months],
        name='Sanctions imposed',
        stackgroup='one',
        line=dict(color=COLORS['red']),
        fillcolor='rgba(220,38,38,0.3)',
    ))
    fig.add_trace(go.Scatter(
        x=all_months,
        y=[warnings_by_month.get(m, 0) for m in all_months],
        name='Warnings only',
        stackgroup='one',
        line=dict(color=COLORS['orange']),
        fillcolor='rgba(234,88,12,0.3)',
    ))
    fig.update_layout(
        title='AI-Related Sanctions & Warnings Over Time',
        xaxis_title='Month',
        yaxis_title='Count',
        template='plotly_white',
        height=500,
    )
    fig.write_html(os.path.join(CHARTS_DIR, 'sanctions_timeline.html'))


def applies_to_breakdown(rows):
    orders = [r for r in rows if is_order(r)]
    opinions = [r for r in rows if is_opinion(r)]

    order_targets = Counter()
    for r in orders:
        val = r.get('applies_to', '')
        if 'Attorney' in val:
            order_targets['Attorneys'] += 1
        if 'Pro Se' in val:
            order_targets['Pro Se Litigants'] += 1
        if 'Any' in val or 'All' in val:
            order_targets['Any Parties'] += 1

    opinion_targets = Counter()
    for r in opinions:
        val = r.get('applies_to', '')
        if 'Attorney' in val:
            opinion_targets['Attorneys'] += 1
        if 'Pro Se' in val:
            opinion_targets['Pro Se Litigants'] += 1
        if 'Any' in val or 'All' in val:
            opinion_targets['Any Parties'] += 1

    targets = ['Attorneys', 'Pro Se Litigants', 'Any Parties']
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=targets,
        y=[order_targets.get(t, 0) for t in targets],
        name='Standing Orders target',
        marker_color=COLORS['blue'],
    ))
    fig.add_trace(go.Bar(
        x=targets,
        y=[opinion_targets.get(t, 0) for t in targets],
        name='Sanctions/warnings involve',
        marker_color=COLORS['red'],
    ))
    fig.update_layout(
        title='Who Orders Target vs. Who Gets Sanctioned',
        yaxis_title='Count',
        barmode='group',
        template='plotly_white',
        height=500,
    )
    fig.write_html(os.path.join(CHARTS_DIR, 'applies_to.html'))


def rg_tags_breakdown(rows):
    tag_counts = Counter()
    for r in rows:
        tags = r.get('applicableTo', [])
        if isinstance(tags, list):
            for tag in tags:
                if tag:
                    tag_counts[tag] += 1

    if not tag_counts:
        return

    sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1])
    labels = [t for t, _ in sorted_tags]
    values = [c for _, c in sorted_tags]

    fig = go.Figure(go.Bar(
        y=labels,
        x=values,
        orientation='h',
        marker_color=COLORS['purple'],
        text=[f'{v}' for v in values],
        textposition='auto',
    ))
    fig.update_layout(
        title=f'Tag Distribution (n={len(rows)})',
        xaxis_title='Count',
        template='plotly_white',
        height=450,
        margin=dict(l=300),
    )
    fig.write_html(os.path.join(CHARTS_DIR, 'rg_tags.html'))


def link_quality(rows):
    categories = Counter()
    for r in rows:
        link = (r.get('link') or '').lower()
        if not link:
            categories['No link'] += 1
        elif 'lexis.com' in link:
            categories['LexisNexis (paywalled)'] += 1
        elif 'westlaw' in link:
            categories['Westlaw (paywalled)'] += 1
        elif 'bloomberglaw' in link:
            categories['Bloomberg (paywalled)'] += 1
        elif 'legalaigovernance.com/tracker/cases' in link:
            categories['Generic tracker'] += 1
        elif 'ropesgray.com' in link and '/states/' in link:
            categories['R&G state page'] += 1
        else:
            categories['Free direct link'] += 1

    colors_map = {
        'Free direct link': COLORS['green'],
        'R&G state page': COLORS['lightblue'],
        'Generic tracker': COLORS['gray'],
        'LexisNexis (paywalled)': COLORS['red'],
        'Westlaw (paywalled)': COLORS['orange'],
        'Bloomberg (paywalled)': '#7c3aed',
        'No link': '#d1d5db',
    }

    labels = list(categories.keys())
    values = list(categories.values())
    colors = [colors_map.get(l, COLORS['gray']) for l in labels]

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        marker_colors=colors,
        textinfo='label+value+percent',
        hole=0.3,
    ))
    fig.update_layout(
        title=f'Link Quality Distribution (n={len(rows)})',
        template='plotly_white',
        height=500,
    )
    fig.write_html(os.path.join(CHARTS_DIR, 'link_quality.html'))


def pro_se_vs_attorney(rows):
    opinions = [r for r in rows if is_opinion(r)]

    pro_se_by_month = Counter()
    attorney_by_month = Counter()

    for r in opinions:
        ym = r.get('date', '')
        if not ym:
            continue
        applies = r.get('applies_to', '')
        if 'Pro Se' in applies:
            pro_se_by_month[ym] += 1
        elif 'Attorney' in applies:
            attorney_by_month[ym] += 1

    all_months = sorted(set(list(pro_se_by_month.keys()) + list(attorney_by_month.keys())))

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=all_months,
        y=[pro_se_by_month.get(m, 0) for m in all_months],
        name='Pro Se Litigants',
        marker_color=COLORS['orange'],
    ))
    fig.add_trace(go.Bar(
        x=all_months,
        y=[attorney_by_month.get(m, 0) for m in all_months],
        name='Attorneys',
        marker_color=COLORS['blue'],
    ))
    fig.update_layout(
        title='AI Enforcement: Pro Se Litigants vs. Attorneys Over Time',
        xaxis_title='Month',
        yaxis_title='Count',
        barmode='stack',
        template='plotly_white',
        height=500,
        legend=dict(x=0.01, y=0.99),
    )
    fig.write_html(os.path.join(CHARTS_DIR, 'pro_se_vs_attorney.html'))


def consequence_severity(rows):
    opinions = [r for r in rows if is_opinion(r)]

    data_points = {'Pro Se': {'warning': 0, 'sanctions': 0},
                   'Attorney': {'warning': 0, 'sanctions': 0}}

    for r in opinions:
        applies = r.get('applies_to', '')
        if 'Pro Se' in applies:
            if is_sanction(r):
                data_points['Pro Se']['sanctions'] += 1
            elif is_warning(r):
                data_points['Pro Se']['warning'] += 1
        elif 'Attorney' in applies:
            if is_sanction(r):
                data_points['Attorney']['sanctions'] += 1
            elif is_warning(r):
                data_points['Attorney']['warning'] += 1

    cats = ['Pro Se', 'Attorney']
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=cats,
        y=[data_points[c]['warning'] for c in cats],
        name='Warning only',
        marker_color=COLORS['orange'],
    ))
    fig.add_trace(go.Bar(
        x=cats,
        y=[data_points[c]['sanctions'] for c in cats],
        name='Sanctions imposed',
        marker_color=COLORS['red'],
    ))
    fig.update_layout(
        title='Consequence Severity: Pro Se vs. Attorneys',
        yaxis_title='Count',
        barmode='group',
        template='plotly_white',
        height=450,
    )
    fig.write_html(os.path.join(CHARTS_DIR, 'consequence_severity.html'))


def sanction_type_distribution(rows):
    """Horizontal bar: breakdown of sanction types across all classified entries."""
    type_counts = Counter()
    for r in rows:
        st = r.get('sanction_types')
        if st and st.get('types'):
            for t in st['types']:
                type_counts[t] += 1

    if not type_counts:
        return

    sorted_types = sorted(type_counts.items(), key=lambda x: x[1])
    labels = [SANCTION_TYPE_LABELS.get(t, t) for t, _ in sorted_types]
    values = [c for _, c in sorted_types]

    type_colors = {
        'Monetary': COLORS['red'],
        'Dismissal': COLORS['orange'],
        'Striking': COLORS['amber'],
        'Bar Referral': COLORS['purple'],
        'CLE Required': COLORS['teal'],
        'Show Cause': COLORS['blue'],
        'Admonishment': COLORS['gray'],
        'Contempt': '#991b1b',
    }
    bar_colors = [type_colors.get(l, COLORS['gray']) for l in labels]

    fig = go.Figure(go.Bar(
        y=labels,
        x=values,
        orientation='h',
        marker_color=bar_colors,
        text=[f'{v}' for v in values],
        textposition='auto',
    ))

    total = sum(1 for r in rows if r.get('sanction_types'))
    fig.update_layout(
        title=f'Sanction Type Distribution (n={total} classified entries)',
        xaxis_title='Count',
        template='plotly_white',
        height=400,
        margin=dict(l=150),
    )
    fig.write_html(os.path.join(CHARTS_DIR, 'sanction_types.html'))


def sanction_amounts(rows):
    """Bar chart: monetary sanction amounts (sought vs awarded)."""
    sought = []
    awarded = []
    labels = []

    for r in rows:
        st = r.get('sanction_types')
        if not st or 'monetary' not in (st.get('types') or []):
            continue
        s = st.get('amount_sought')
        a = st.get('amount_awarded')
        if not s and not a:
            continue

        def parse_amount(val):
            if not val:
                return 0
            val = val.replace('$', '').replace(',', '').strip()
            try:
                return float(val)
            except ValueError:
                return 0

        s_val = parse_amount(s)
        a_val = parse_amount(a)
        if s_val > 0 or a_val > 0:
            label = r.get('judge', r.get('name', ''))[:30]
            labels.append(label)
            sought.append(s_val)
            awarded.append(a_val)

    if not labels:
        return

    indices = sorted(range(len(awarded)), key=lambda i: awarded[i] or sought[i], reverse=True)[:20]
    labels = [labels[i] for i in indices]
    sought = [sought[i] for i in indices]
    awarded = [awarded[i] for i in indices]
    labels.reverse()
    sought.reverse()
    awarded.reverse()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels, x=sought,
        name='Amount Sought',
        orientation='h',
        marker_color=COLORS['lightred'],
    ))
    fig.add_trace(go.Bar(
        y=labels, x=awarded,
        name='Amount Awarded',
        orientation='h',
        marker_color=COLORS['red'],
    ))
    fig.update_layout(
        title='Monetary Sanctions: Sought vs. Awarded (Top 20)',
        xaxis_title='Amount ($)',
        barmode='group',
        template='plotly_white',
        height=600,
        margin=dict(l=250),
    )
    fig.write_html(os.path.join(CHARTS_DIR, 'sanction_amounts.html'))


def write_summary_stats(rows):
    total = len(rows)
    dt = Counter(r['type'] for r in rows if r.get('type'))
    orders = [r for r in rows if is_order(r)]
    opinions = [r for r in rows if is_opinion(r)]

    sanctions = [r for r in opinions if is_sanction(r)]
    warnings = [r for r in opinions if is_warning(r)]

    link_free = sum(1 for r in rows if r.get('link') and
                    'lexis.com' not in r['link'].lower() and
                    'westlaw' not in r['link'].lower() and
                    'bloomberglaw' not in r['link'].lower())
    link_paywalled = sum(1 for r in rows if r.get('link') and
                         ('lexis.com' in r['link'].lower() or
                          'westlaw' in r['link'].lower() or
                          'bloomberglaw' in r['link'].lower()))

    tag_counts = Counter()
    for r in rows:
        tags = r.get('applicableTo', [])
        if isinstance(tags, list):
            for tag in tags:
                if tag:
                    tag_counts[tag] += 1

    sanction_type_counts = Counter()
    for r in rows:
        st = r.get('sanction_types')
        if st and st.get('types'):
            for t in st['types']:
                sanction_type_counts[t] += 1

    stats = {
        'total_entries': total,
        'document_types': dict(dt),
        'total_orders_rules': len(orders),
        'total_opinions': len(opinions),
        'total_sanctions': len(sanctions),
        'total_warnings': len(warnings),
        'date_range': {
            'earliest': min((r['date'] for r in rows if r.get('date')), default=''),
            'latest': max((r['date'] for r in rows if r.get('date')), default=''),
        },
        'states_represented': len(set(r['state'] for r in rows if r.get('state') and r['state'] != '-')),
        'unique_judges': len(set(r['judge'].lower() for r in rows if r.get('judge'))),
        'source_breakdown': dict(Counter(r['source'] for r in rows if r.get('source'))),
        'ai_type': dict(Counter(r['ai_type'] for r in rows if r.get('ai_type'))),
        'link_quality': {
            'free': link_free,
            'paywalled': link_paywalled,
            'free_pct': round(100 * link_free / total, 1) if total else 0,
        },
        'tags': dict(tag_counts.most_common()),
        'sanction_types': dict(sanction_type_counts.most_common()),
        'entries_with_sanction_types': sum(1 for r in rows if r.get('sanction_types')),
    }

    with open(os.path.join(ANALYSIS_DIR, 'summary_stats.json'), 'w') as f:
        json.dump(stats, f, indent=2)

    return stats


def main():
    rows = load_data()
    print(f"Loaded {len(rows)} entries from JSON")

    print("Generating charts...")
    orders_vs_opinions_by_month(rows)
    print("  orders_vs_opinions_monthly.html")

    cumulative_growth(rows)
    print("  cumulative_growth.html")

    by_state(rows)
    print("  by_state.html")

    document_type_breakdown(rows)
    print("  document_types.html")

    requirements_heatmap(rows)
    print("  requirements_breakdown.html")

    categories = enforcement_analysis(rows)
    print("  enforcement_by_order.html")

    sanctions_timeline(rows)
    print("  sanctions_timeline.html")

    applies_to_breakdown(rows)
    print("  applies_to.html")

    rg_tags_breakdown(rows)
    print("  rg_tags.html")

    link_quality(rows)
    print("  link_quality.html")

    pro_se_vs_attorney(rows)
    print("  pro_se_vs_attorney.html")

    consequence_severity(rows)
    print("  consequence_severity.html")

    sanction_type_distribution(rows)
    print("  sanction_types.html")

    sanction_amounts(rows)
    print("  sanction_amounts.html")

    stats = write_summary_stats(rows)
    print("  summary_stats.json")

    print(f"\n{'='*60}")
    print(f"DATASET SUMMARY")
    print(f"{'='*60}")
    print(f"Total entries: {stats['total_entries']}")
    print(f"Date range: {stats['date_range']['earliest']} to {stats['date_range']['latest']}")
    print(f"States: {stats['states_represented']}")
    print(f"Unique judges: {stats['unique_judges']}")
    print(f"Sources: {stats['source_breakdown']}")
    print()
    print(f"Document types:")
    for dt, c in sorted(stats['document_types'].items(), key=lambda x: -x[1]):
        print(f"  {c:3d} {dt}")
    print()
    print(f"Opinions: {stats['total_opinions']} total")
    print(f"  Sanctions imposed: {stats['total_sanctions']}")
    print(f"  Warnings only: {stats['total_warnings']}")
    print(f"  Other/unclear: {stats['total_opinions'] - stats['total_sanctions'] - stats['total_warnings']}")
    print()
    print(f"Sanction types ({stats['entries_with_sanction_types']} classified):")
    for t, c in stats['sanction_types'].items():
        print(f"  {c:3d} {SANCTION_TYPE_LABELS.get(t, t)}")
    print()
    print(f"AI type: {stats['ai_type']}")
    print()
    print(f"Link quality: {stats['link_quality']['free']} free ({stats['link_quality']['free_pct']}%), "
          f"{stats['link_quality']['paywalled']} paywalled")
    print()
    print(f"Enforcement vs standing orders:")
    for cat, counts in categories.items():
        total = sum(counts.values())
        print(f"  {cat:20s}  {total:3d} opinions  (sanctions={counts['sanctions']}, warnings={counts['warning']})")


if __name__ == '__main__':
    main()
