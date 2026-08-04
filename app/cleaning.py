import re
from urllib.parse import urlparse
import pandas as pd

URL_COLUMNS = ('URL', 'LinkedIn URL', 'linkedin_url', 'Profile URL')


def first_existing(columns, candidates):
    lowered = {str(c).strip().lower(): c for c in columns}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def valid_linkedin_url(value):
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlparse(value.strip())
    return parsed.scheme in ('http', 'https') and parsed.netloc.lower().endswith('linkedin.com')


def title_case(value):
    if not isinstance(value, str):
        return ''
    value = re.sub(r'\s+', ' ', value).strip()
    return value.title() if value.isupper() else value


def clean_connections(frame):
    frame = frame.copy()
    frame.columns = [str(c).strip() for c in frame.columns]
    url_col = first_existing(frame.columns, URL_COLUMNS)
    if not url_col:
        raise ValueError('No LinkedIn URL column found. Expected URL, LinkedIn URL, linkedin_url, or Profile URL.')
    for col in frame.select_dtypes(include='object'):
        frame[col] = frame[col].fillna('').astype(str).str.strip().str.replace(r'\s+', ' ', regex=True)
    first, last = first_existing(frame.columns, ('First Name', 'first_name')), first_existing(frame.columns, ('Last Name', 'last_name'))
    if first: frame[first] = frame[first].map(title_case)
    if last: frame[last] = frame[last].map(title_case)
    frame['linkedin_url'] = frame[url_col].str.replace(r'\?.*$', '', regex=True).str.rstrip('/')
    frame['valid_linkedin_url'] = frame['linkedin_url'].map(valid_linkedin_url)
    frame = frame[frame['valid_linkedin_url']].drop_duplicates('linkedin_url', keep='last')
    return frame.reset_index(drop=True)

