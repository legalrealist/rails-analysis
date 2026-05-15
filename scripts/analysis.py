#!/usr/bin/env python3
"""Basic analysis and charts for the enriched AI court orders dataset."""

import csv
import json
import os
from collections import Counter, defaultdict
import plotly.graph_objects as go
from plotly.subplots import make_subplots

INPUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'orders_enriched.csv')
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
}


def load_data():
    with open(INPUT, encoding='utf-8') as f:
        return list(csv.DictReader(f))


def orders_vs_opinions_by_month(rows):
    """Bar chart: new standing orders vs judicial opinions per month."""
    orders_by_month = Counter()
    opinions_by_month = Counter()

    for r in rows:
        ym = r['date_yyyy_mm']
        if not ym:
            continue
        if r['document_type'] in ('Standing Order', 'Local Rules', 'Administrative Order', 'Practice Direction'):
            orders_by_month[ym] += 1
        elif r['document_type'] == 'Judicial Opinion':
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
    """Line chart: cumulative standing orders and opinions over time."""
    orders_by_month = Counter()
    opinions_by_month = Counter()

    for r in rows:
        ym = r['date_yyyy_mm']
        if not ym:
            continue
        if r['document_type'] in ('Standing Order', 'Local Rules', 'Administrative Order', 'Practice Direction'):
            orders_by_month[ym] += 1
        elif r['document_type'] == 'Judicial Opinion':
            opinions_by_month[ym] += 1

    all_months = sorted(set(list(orders_by_month.keys()) + list(opinions_by_month.keys())))

    cum_orders = []
    cum_opinions = []
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
    """Horizontal bar: top 20 states by total activity, split by type."""
    state_orders = Counter()
    state_opinions = Counter()

    for r in rows:
        st = r['state']
        if not st or st == '-':
            continue
        if r['document_type'] in ('Standing Order', 'Local Rules', 'Administrative Order', 'Practice Direction'):
            state_orders[st] += 1
        elif r['document_type'] == 'Judicial Opinion':
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
    """Pie chart of document types."""
    dt = Counter(r['document_type'] for r in rows if r['document_type'])

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
    """Heatmap: which requirements do standing orders impose?"""
    orders = [r for r in rows if r['document_type'] in ('Standing Order', 'Local Rules', 'Administrative Order')]

    req_cols = [
        ('Disclose AI use', 'disclose_ai_use_w_each_filing'),
        ('Disclose tool used', 'disclose_ai_tool_used'),
        ('Disclose how used', 'disclose_how_ai_tool_used'),
        ('ID sections drafted', 'identify_sections_drafted_with_ai'),
        ('Verify accuracy process', 'disclose_process_used_to_check_accuracy'),
        ('Certify accuracy/non-use\n(each filing)', 'certify_accuracy_non_use_w_each_filing'),
        ('Certify accuracy\n(if AI used)', 'certify_accuracy_w_each_filing_if_ai_used'),
        ('Certify no unauthorized\ndisclosure', 'certify_no_unauthorized_disclosure'),
        ('Retain AI prompts', 'maintain_ai_prompt_records'),
        ('Protect proprietary info', 'proprietary_info_nondisclosure_req'),
        ('Just a warning', 'just_a_warning'),
        ('Prohibits AI', 'prohibited'),
        ('References FRCP 11+', 'references_other_procedural_rules'),
    ]

    labels = [l for l, _ in req_cols]
    counts = []
    for label, col in req_cols:
        if col == 'references_other_procedural_rules':
            c = sum(1 for r in orders if r.get(col, '') and r[col] != 'No')
        elif col in ('disclose_ai_use_w_each_filing', 'certify_accuracy_non_use_w_each_filing'):
            c = sum(1 for r in orders if r.get(col, '') == 'Yes')
        else:
            c = sum(1 for r in orders if r.get(col, '') and r[col] not in ('No', ''))
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
    """Bar chart: enforcement with/without standing orders."""
    judges = defaultdict(lambda: {'orders': [], 'opinions': []})
    for r in rows:
        ln = r['judge_last_name'].lower().strip()
        court = r['court_abbreviation'].strip()
        if not ln:
            continue
        key = (ln, court)
        if r['document_type'] in ('Standing Order', 'Local Rules', 'Administrative Order', 'Practice Direction'):
            judges[key]['orders'].append(r)
        elif r['document_type'] == 'Judicial Opinion':
            judges[key]['opinions'].append(r)

    districts_with_orders = set()
    for (ln, court), v in judges.items():
        if v['orders'] and court:
            districts_with_orders.add(court)

    categories = {'Same judge': {'sanctions': 0, 'warning': 0, 'other': 0},
                  'Same district': {'sanctions': 0, 'warning': 0, 'other': 0},
                  'No order': {'sanctions': 0, 'warning': 0, 'other': 0}}

    for (ln, court), v in judges.items():
        for op in v['opinions']:
            if v['orders']:
                cat = 'Same judge'
            elif court in districts_with_orders:
                cat = 'Same district'
            else:
                cat = 'No order'

            if op.get('rg_consequences_attorneys') == 'checked' or op.get('rg_consequences_parties') == 'checked':
                categories[cat]['sanctions'] += 1
            elif op.get('just_a_warning') == 'checked':
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
    """Stacked area: sanctions vs warnings over time."""
    sanctions_by_month = Counter()
    warnings_by_month = Counter()

    for r in rows:
        if r['document_type'] != 'Judicial Opinion':
            continue
        ym = r['date_yyyy_mm']
        if not ym:
            continue
        if r.get('rg_consequences_attorneys') == 'checked' or r.get('rg_consequences_parties') == 'checked':
            sanctions_by_month[ym] += 1
        elif r.get('just_a_warning') == 'checked':
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
    """Who do the orders apply to?"""
    orders = [r for r in rows if r['document_type'] in ('Standing Order', 'Local Rules', 'Administrative Order')]
    opinions = [r for r in rows if r['document_type'] == 'Judicial Opinion']

    # For orders
    order_targets = Counter()
    for r in orders:
        val = r['applies_to']
        if 'Attorneys' in val:
            order_targets['Attorneys'] += 1
        if 'Pro Se' in val:
            order_targets['Pro Se Litigants'] += 1
        if 'Any Parties' in val:
            order_targets['Any Parties'] += 1

    # For opinions - who got sanctioned/warned
    opinion_targets = Counter()
    for r in opinions:
        val = r['applies_to']
        if 'Attorneys' in val:
            opinion_targets['Attorneys'] += 1
        if 'Pro Se' in val:
            opinion_targets['Pro Se Litigants'] += 1
        if 'Any Parties' in val:
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
    """Horizontal bar: R&G applicableTo tag distribution across all entries."""
    tag_counts = Counter()
    for r in rows:
        tags = r.get('rg_applicable_to', '')
        if tags:
            for tag in tags.split('|'):
                tag = tag.strip()
                if tag:
                    tag_counts[tag] += 1

    if not tag_counts:
        return

    # Sort by count
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
        title=f'R&G Tag Distribution (n={len(rows)})',
        xaxis_title='Count',
        template='plotly_white',
        height=450,
        margin=dict(l=300),
    )
    fig.write_html(os.path.join(CHARTS_DIR, 'rg_tags.html'))


def link_quality(rows):
    """Pie chart: link quality — free vs paywalled vs generic."""
    categories = Counter()
    for r in rows:
        link = r.get('link_to_source', '').lower()
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
    """Stacked bar over time: sanctions/warnings by pro se vs attorney."""
    opinions = [r for r in rows if r['document_type'] == 'Judicial Opinion']

    pro_se_by_month = Counter()
    attorney_by_month = Counter()

    for r in opinions:
        ym = r['date_yyyy_mm']
        if not ym:
            continue
        applies = r.get('applies_to', '')
        if 'Pro Se' in applies:
            pro_se_by_month[ym] += 1
        elif 'Attorneys' in applies:
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
    """Grouped bar: consequence type (warning/sanctions) by who gets hit."""
    opinions = [r for r in rows if r['document_type'] == 'Judicial Opinion']

    data_points = {'Pro Se': {'warning': 0, 'sanctions': 0},
                   'Attorney': {'warning': 0, 'sanctions': 0}}

    for r in opinions:
        applies = r.get('applies_to', '')
        is_sanction = (r.get('rg_consequences_attorneys') == 'checked' or
                       r.get('rg_consequences_parties') == 'checked')
        is_warning = r.get('just_a_warning') == 'checked'

        if 'Pro Se' in applies:
            if is_sanction:
                data_points['Pro Se']['sanctions'] += 1
            elif is_warning:
                data_points['Pro Se']['warning'] += 1
        elif 'Attorneys' in applies:
            if is_sanction:
                data_points['Attorney']['sanctions'] += 1
            elif is_warning:
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


def write_summary_stats(rows):
    """Write summary statistics JSON."""
    total = len(rows)
    dt = Counter(r['document_type'] for r in rows)
    orders = [r for r in rows if r['document_type'] in ('Standing Order', 'Local Rules', 'Administrative Order', 'Practice Direction')]
    opinions = [r for r in rows if r['document_type'] == 'Judicial Opinion']

    sanctions = [r for r in opinions
                 if r.get('rg_consequences_attorneys') == 'checked' or r.get('rg_consequences_parties') == 'checked']
    warnings = [r for r in opinions if r.get('just_a_warning') == 'checked']

    # Link quality
    link_free = sum(1 for r in rows if r.get('link_to_source') and
                    'lexis.com' not in r['link_to_source'].lower() and
                    'westlaw' not in r['link_to_source'].lower() and
                    'bloomberglaw' not in r['link_to_source'].lower())
    link_paywalled = sum(1 for r in rows if r.get('link_to_source') and
                         ('lexis.com' in r['link_to_source'].lower() or
                          'westlaw' in r['link_to_source'].lower() or
                          'bloomberglaw' in r['link_to_source'].lower()))

    # R&G tags
    tag_counts = Counter()
    for r in rows:
        tags = r.get('rg_applicable_to', '')
        if tags:
            for tag in tags.split('|'):
                tag = tag.strip()
                if tag:
                    tag_counts[tag] += 1

    stats = {
        'total_entries': total,
        'document_types': dict(dt),
        'total_orders_rules': len(orders),
        'total_opinions': len(opinions),
        'total_sanctions': len(sanctions),
        'total_warnings': len(warnings),
        'date_range': {
            'earliest': min((r['date_yyyy_mm'] for r in rows if r['date_yyyy_mm']), default=''),
            'latest': max((r['date_yyyy_mm'] for r in rows if r['date_yyyy_mm']), default=''),
        },
        'states_represented': len(set(r['state'] for r in rows if r['state'] and r['state'] != '-')),
        'unique_judges': len(set(r['judge_last_name'].lower() for r in rows if r['judge_last_name'])),
        'source_breakdown': dict(Counter(r['source'] for r in rows)),
        'ai_type': dict(Counter(r['ai_type'] for r in rows if r['ai_type'])),
        'link_quality': {
            'free': link_free,
            'paywalled': link_paywalled,
            'free_pct': round(100 * link_free / total, 1) if total else 0,
        },
        'rg_tags': dict(tag_counts.most_common()),
        'top_requirements_in_orders': {},
    }

    req_cols = [
        ('disclose_ai_use_w_each_filing', 'Yes'),
        ('certify_accuracy_w_each_filing_if_ai_used', 'checked'),
        ('certify_accuracy_non_use_w_each_filing', 'Yes'),
        ('just_a_warning', 'checked'),
        ('maintain_ai_prompt_records', 'checked'),
        ('prohibited', 'checked'),
    ]
    for col, match_val in req_cols:
        count = sum(1 for r in orders if r.get(col, '') == match_val)
        stats['top_requirements_in_orders'][col] = {'count': count, 'pct': round(100 * count / len(orders), 1) if orders else 0}

    with open(os.path.join(ANALYSIS_DIR, 'summary_stats.json'), 'w') as f:
        json.dump(stats, f, indent=2)

    return stats


def main():
    rows = load_data()
    print(f"Loaded {len(rows)} rows")

    # Generate all charts
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

    stats = write_summary_stats(rows)
    print("  summary_stats.json")

    # Print summary
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
    print(f"AI type: {stats['ai_type']}")
    print()
    print(f"Link quality: {stats['link_quality']['free']} free ({stats['link_quality']['free_pct']}%), "
          f"{stats['link_quality']['paywalled']} paywalled")
    print()
    print(f"R&G tags: {dict(list(stats['rg_tags'].items())[:5])}")
    print()
    print(f"Enforcement vs standing orders:")
    for cat, counts in categories.items():
        total = sum(counts.values())
        print(f"  {cat:20s}  {total:3d} opinions  (sanctions={counts['sanctions']}, warnings={counts['warning']})")


if __name__ == '__main__':
    main()
