from datetime import datetime
import pandas as pd
from .config import EXPORT_DIR
from .database import connection


def generated_exports():
    return sorted([p for p in EXPORT_DIR.iterdir() if p.is_file() and p.name != '.gitkeep'], key=lambda p: p.stat().st_mtime, reverse=True)


def export_dataset(queries=None):
    queries = queries or []
    with connection() as conn:
        data = pd.read_sql_query('SELECT * FROM profiles', conn)
        if queries:
            placeholders = ','.join('?' for _ in queries)
            results = pd.read_sql_query(f'''SELECT r.research_query, r.research_area, r.matched_keywords, r.relevance_score,
                r.relevant_flag, r.confidence, r.academic_expert, r.industry_expert, r.security_expert,
                r.architecture_expert, r.potential_validator, r.validation_priority, p.*
                FROM relevance r JOIN profiles p ON p.id=r.profile_id
                WHERE r.research_query IN ({placeholders})''', conn, params=queries)
        else:
            results = pd.DataFrame()
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_path, xlsx_path = EXPORT_DIR / f'linkedin_research_{stamp}.csv', EXPORT_DIR / f'linkedin_research_{stamp}.xlsx'
    data.to_csv(csv_path, index=False)
    relevant = results[results.get('relevant_flag', pd.Series(index=results.index, dtype=str)).eq('Yes')] if not results.empty else results
    summary = pd.DataFrame({'Metric':['Total profiles','Reviewed profiles','Selected research queries','Relevant matches','Potential validators'],
       'Value':[len(data), int((data.profile_status=='Reviewed').sum()), len(queries), len(relevant),
                int((relevant.get('potential_validator',pd.Series(dtype=str))=='Yes').sum())]})
    with pd.ExcelWriter(xlsx_path, engine='openpyxl') as writer:
        data.to_excel(writer, sheet_name='Master Data', index=False)
        if queries:
            results.to_excel(writer, sheet_name='Research Results', index=False)
        relevant.to_excel(writer, sheet_name='Relevant Experts', index=False)
        summary.to_excel(writer, sheet_name='Research Summary', index=False)
    return csv_path, xlsx_path
