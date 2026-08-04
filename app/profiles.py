import json
import re
from datetime import date
from dateutil import parser
from .database import connection, utcnow

SENIORITY = [(r'\b(chief|cxo|ceo|cto|cio|vp|vice president|president)\b', 'C-Level / VP'),
             (r'\b(director|head of)\b', 'Director'), (r'\b(manager|principal)\b', 'Manager'),
             (r'\b(architect|lead|staff)\b', 'Lead / Architect'), (r'\b(senior|sr\.?|consultant)\b', 'Senior'),
             (r'\b(intern|trainee|junior|jr\.?)\b', 'Junior')]


def seniority(text):
    for pattern, label in SENIORITY:
        if re.search(pattern, text or '', re.I): return label
    return 'Mid-Level'


def upsert_imported_profiles(frame, source='CSV import'):
    columns = {c.lower(): c for c in frame.columns}
    def value(row, *names):
        for name in names:
            if name.lower() in columns: return str(row[columns[name.lower()]] or '').strip()
        return ''
    count = 0
    with connection() as conn:
        for _, row in frame.iterrows():
            first, last = value(row, 'First Name', 'first_name'), value(row, 'Last Name', 'last_name')
            full_name = value(row, 'Full Name', 'full_name') or f'{first} {last}'.strip()
            payload = (value(row, 'linkedin_url'), full_name, first, last, value(row, 'Email Address', 'email'),
                       value(row, 'Company', 'company'), value(row, 'Position', 'position'),
                       value(row, 'Connected On', 'connected_on'), source, row.to_json(), utcnow(), utcnow())
            conn.execute("""INSERT INTO profiles(linkedin_url,full_name,first_name,last_name,email,imported_company,
              imported_position,connected_on,source,raw_row_json,last_updated,created_at)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(linkedin_url) DO UPDATE SET full_name=excluded.full_name, first_name=excluded.first_name,
              last_name=excluded.last_name, email=excluded.email, imported_company=excluded.imported_company,
              imported_position=excluded.imported_position, connected_on=excluded.connected_on,
              source=excluded.source, raw_row_json=excluded.raw_row_json, last_updated=excluded.last_updated""", payload)
            count += 1
    return count


def calculate_experience(entries):
    intervals, companies, current_durations = [], set(), []
    today = date.today()
    for entry in entries:
        start = entry.get('start', '')
        end = entry.get('end', '')
        try:
            start_date = parser.parse(start, default=date(2000, 1, 1))
            end_date = today if not end or end.lower() == 'present' else parser.parse(end, default=date(today.year, 1, 1))
            start_date = start_date.date() if hasattr(start_date, 'date') else start_date
            end_date = end_date.date() if hasattr(end_date, 'date') else end_date
            if end_date >= start_date:
                duration = (end_date.year-start_date.year)*12 + end_date.month-start_date.month
                intervals.append((start_date, end_date)); companies.add(entry.get('company', '').strip().lower())
                if not end or str(end).lower() == 'present': current_durations.append(duration)
        except (TypeError, ValueError, OverflowError):
            continue
    if not intervals: return {'years': None, 'start_year': None, 'companies': 0, 'roles': 0, 'longest': None, 'current': None}
    intervals.sort(); merged = []
    for start, end in intervals:
        if not merged or start > merged[-1][1]: merged.append([start, end])
        elif end > merged[-1][1]: merged[-1][1] = end
    months = sum((end.year-start.year)*12 + end.month-start.month for start, end in merged)
    durations = [(end.year-start.year)*12 + end.month-start.month for start, end in intervals]
    return {'years': round(months/12, 1), 'start_year': min(x[0] for x in intervals).year, 'companies': len(companies-{''}),
            'roles': len(intervals), 'longest': max(durations), 'current': max(current_durations) if current_durations else None}


def save_profile_review(profile_id, values, experience_entries):
    stats = calculate_experience(experience_entries)
    current_title = values.get('current_position', '')
    with connection() as conn:
        conn.execute("""UPDATE profiles SET headline=?,location=?,about=?,skills=?,current_position=?,current_company=?,
          experience_json=?,career_start_year=?,total_experience_years=?,number_of_roles=?,number_of_companies=?,
          longest_tenure_months=?,current_tenure_months=?,seniority_level=?,profile_status='Reviewed',last_updated=? WHERE id=?""",
          (values.get('headline',''),values.get('location',''),values.get('about',''),values.get('skills',''),current_title,
           values.get('current_company',''),json.dumps(experience_entries),stats['start_year'],stats['years'],stats['roles'],
           stats['companies'],stats['longest'],stats['current'],seniority(current_title),utcnow(),profile_id))
