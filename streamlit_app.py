import json
import subprocess
import sys
import pandas as pd
import streamlit as st
from app.config import ROOT
from app.database import (initialise, connection, create_run, update_run, latest_run, active_run, log,
                          replace_dataset, delete_profile, delete_research_query)
from app.cleaning import clean_connections
from app.profiles import upsert_imported_profiles, save_profile_review
from app.scoring import score_profiles
from app.exporting import export_dataset, generated_exports

st.set_page_config(page_title='Research Intelligence', page_icon='🔎', layout='wide')
initialise()

def all_profiles():
    with connection() as conn:
        return pd.read_sql_query('SELECT * FROM profiles ORDER BY id DESC', conn)


def safe_text(value):
    """Turn database NULL/NaN values into empty form fields."""
    return '' if value is None or pd.isna(value) else str(value)

def parse_roles(text):
    roles = []
    for line in text.splitlines():
        parts = [part.strip() for part in line.split('|')]
        if len(parts) >= 3:
            roles.append({'company': parts[0], 'title': parts[1], 'start': parts[2], 'end': parts[3] if len(parts) > 3 else 'Present'})
    return roles


def start_background_scoring(query):
    run_id = create_run('Research scoring', len(all_profiles()), {'query': query, 'mode': 'CSV-first'})
    log(run_id, 'INFO', 'Background scoring queued.')
    subprocess.Popen([sys.executable, '-m', 'app.worker', str(run_id), query], cwd=str(ROOT),
                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return run_id


def latest_query():
    run = latest_run()
    if not run or not run['settings_json']:
        return ''
    return json.loads(run['settings_json']).get('query', '')

st.title('LinkedIn Research Intelligence & Expert Discovery')
st.caption('Start with CSV-based research matching. Profile review is optional and intended only for your shortlisted candidates.')

profiles = all_profiles()
latest = latest_run()
metrics = st.columns(4)
metrics[0].metric('Profiles', len(profiles))
metrics[1].metric('Reviewed', int((profiles.profile_status == 'Reviewed').sum()) if not profiles.empty else 0)
metrics[2].metric('Pending review', int((profiles.profile_status == 'Pending').sum()) if not profiles.empty else 0)
metrics[3].metric('Last run', latest['status'] if latest else 'Not started')

active = active_run()
with st.sidebar:
    st.header('Quick research run')
    quick_query = st.text_area('Your research topics / keywords', value=st.session_state.get('research_query', latest_query()),
                                key='research_query', placeholder='DevSecOps, Secure Scrum, Software Architecture')
    st.caption('Scores existing CSV fields: Position, Company, Headline, and any reviewed details.')
    auto_run_after_import = st.checkbox('Auto-run after next CSV import', value=False)
    if active:
        done, total = active['processed'], active['total']
        st.progress(done / total if total else 0, text=f"{active['status']}: {done:,} / {total:,}")
        st.caption(f"Current: {active['current_item'] or 'Preparing…'}")
        controls = st.columns(2)
        if active['status'] == 'Running' and controls[0].button('Pause', use_container_width=True):
            update_run(active['id'], status='Paused', message='Paused by user')
            st.rerun()
        elif active['status'] == 'Paused' and controls[0].button('Resume', use_container_width=True):
            update_run(active['id'], status='Running', message='Resumed by user')
            st.rerun()
        if active['status'] in ('Running', 'Paused') and controls[1].button('Stop', use_container_width=True):
            update_run(active['id'], status='Stop requested', message='Stop requested by user')
            st.rerun()
        elif active['status'] == 'Stop requested':
            controls[1].button('Stopping…', disabled=True, use_container_width=True)
        if st.button('Refresh job status', use_container_width=True):
            st.rerun()
    elif st.button('Start scoring all imported profiles', type='primary', use_container_width=True, disabled=profiles.empty):
        if not quick_query.strip():
            st.error('Enter at least one research topic or keyword.')
        else:
            start_background_scoring(quick_query)
            st.success('Scoring started in the background. This page will show live progress.')
            st.rerun()
    if not active and latest_query() and st.button('Re-run last query', use_container_width=True, disabled=profiles.empty):
        start_background_scoring(latest_query())
        st.rerun()

tab_import, tab_review, tab_score, tab_export, tab_manage = st.tabs(['1. Import & clean', '2. Review queue', '3. Research matching', '4. Export', '5. Data manager'])

with tab_import:
    st.subheader('Choose an input source')
    st.info('CSV import is the supported acquisition route. Download your connections using LinkedIn’s data export, then upload the CSV here. The connections-page option is a browser-assisted review mode; it does not bulk collect or scrape data.')
    mode = st.radio('Input source', ['Connections CSV', 'Browser-assisted connections page'], horizontal=True)
    if mode == 'Connections CSV':
        upload = st.file_uploader('Connections CSV', type=['csv'])
        import_mode = st.radio('When importing this CSV', ['Replace all saved profiles (recommended)', 'Merge with saved profiles'], horizontal=True)
        if import_mode.startswith('Replace'):
            st.warning('Replace removes all saved profiles, reviews, research scores, and job history before importing this file.')
        if upload and st.button('Clean and import connections', type='primary'):
            try:
                if active:
                    raise ValueError('Pause or stop the current scoring job before changing the dataset.')
                raw = pd.read_csv(upload)
                cleaned = clean_connections(raw)
                if import_mode.startswith('Replace'):
                    replace_dataset()
                run_id = create_run('CSV import', len(cleaned), {'source_file': upload.name})
                saved = upsert_imported_profiles(cleaned)
                update_run(run_id, status='Completed', processed=saved, succeeded=saved, message='Imported and de-duplicated')
                log(run_id, 'INFO', f'Imported {saved} valid, unique profile URLs.')
                st.success(f'Imported {saved} unique profiles. {len(raw) - len(cleaned)} invalid or duplicate rows were removed.')
                if auto_run_after_import and quick_query.strip():
                    start_background_scoring(quick_query)
                    st.info('Automatic research scoring has started in the background.')
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    else:
        st.write('Open the connections page in your normal browser, then use its official export/download option. Upload the resulting CSV here for cleaning and research processing.')
        st.link_button('Open LinkedIn Connections', 'https://www.linkedin.com/mynetwork/invite-connect/connections/')


with tab_review:
    st.subheader('Fast enrichment for shortlisted profiles')
    if profiles.empty:
        st.warning('Import connections first.')
    else:
        with connection() as conn:
            recent_queries = [r[0] for r in conn.execute('SELECT DISTINCT research_query FROM relevance ORDER BY created_at DESC').fetchall()]
            shortlist_query = st.selectbox('Shortlist based on research run', ['All pending profiles'] + recent_queries)
            if shortlist_query == 'All pending profiles':
                candidates = profiles[profiles.profile_status != 'Reviewed']
                queue_label = 'all pending profiles'
            else:
                shortlist = pd.read_sql_query("""SELECT p.* FROM profiles p JOIN relevance r ON r.profile_id=p.id
                    WHERE r.research_query=? AND r.relevant_flag='Yes' AND p.profile_status != 'Reviewed'
                    ORDER BY r.validation_priority='High' DESC, r.relevance_score DESC""", conn, params=[shortlist_query])
                candidates = shortlist
                queue_label = 'relevant candidates remaining'
        reviewed = len(profiles) - len(profiles[profiles.profile_status != 'Reviewed'])
        st.progress(reviewed / len(profiles), text=f'{reviewed:,} reviewed; {len(candidates):,} {queue_label}')
        if candidates.empty:
            st.success('No candidates remain in this queue.')
            st.stop()
        selected_id = st.selectbox('Profile to review', candidates.id, format_func=lambda x: f"{profiles.set_index('id').loc[x, 'full_name']} — {profiles.set_index('id').loc[x, 'linkedin_url']}")
        selected = profiles.set_index('id').loc[selected_id]
        st.link_button('Open profile in your browser', selected.linkedin_url)
        with st.form('review_form'):
            left, right = st.columns(2)
            headline = left.text_input('Headline', safe_text(selected.headline))
            location = right.text_input('Location', safe_text(selected.location))
            current_position = left.text_input('Current position', safe_text(selected.current_position) or safe_text(selected.imported_position))
            current_company = right.text_input('Current company', safe_text(selected.current_company) or safe_text(selected.imported_company))
            about = st.text_area('About / notes', safe_text(selected.about), height=90)
            skills = st.text_input('Skills (comma-separated)', safe_text(selected.skills))
            existing = json.loads(safe_text(selected.experience_json) or '[]')
            roles_text = st.text_area('Experience history — one role per line: Company | Title | Start (e.g. Jan 2020) | End (or Present)',
                                      '\n'.join(' | '.join([r.get('company',''),r.get('title',''),r.get('start',''),r.get('end','')]) for r in existing), height=150)
            if st.form_submit_button('Save review and recalculate experience', type='primary'):
                save_profile_review(int(selected_id), {'headline':headline,'location':location,'current_position':current_position,
                    'current_company':current_company,'about':about,'skills':skills}, parse_roles(roles_text))
                st.success('Saved. Experience totals and seniority were recalculated.')
                st.rerun()

with tab_score:
    st.subheader('Research relevance and expert classification')
    st.info('For the quickest workflow, use “Quick research run” in the left sidebar. It processes every imported CSV record and shows live progress.')
    query = st.text_area('Research areas / keywords', placeholder='DevSecOps, Secure Scrum, Software Architecture, MDSPL')
    st.caption('Uses a local TF-IDF semantic similarity model plus exact keyword matches. No profile data is sent to an external AI service.')
    if st.button('Start a background scoring run from this tab', disabled=profiles.empty or active is not None):
        try:
            if not query.strip():
                raise ValueError('Enter at least one keyword or research area.')
            start_background_scoring(query)
            st.success('Background scoring started. Monitor it from the sidebar.')
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

with tab_export:
    st.subheader('Export research dataset')
    with connection() as conn:
        queries = [r[0] for r in conn.execute('SELECT DISTINCT research_query FROM relevance ORDER BY created_at DESC').fetchall()]
    export_queries = st.multiselect('Include relevance results for (choose one or more)', queries,
                                    help='The Excel file will contain all selected queries in one Research Results sheet.')
    if st.button('Create Excel and CSV', type='primary', disabled=profiles.empty):
        csv_path, xlsx_path = export_dataset(export_queries)
        st.success('Exports created.')
        st.download_button('Download CSV', csv_path.read_bytes(), csv_path.name, 'text/csv')
        st.download_button('Download Excel', xlsx_path.read_bytes(), xlsx_path.name, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    st.subheader('Recent activity')
    with connection() as conn:
        events = pd.read_sql_query('SELECT created_at, run_id, level, message FROM events ORDER BY id DESC LIMIT 20', conn)
    st.dataframe(events, use_container_width=True, hide_index=True)

with tab_manage:
    st.subheader('Data manager')
    st.info('Use this tab to manage stored profiles, research results, and generated exports. Changes are permanent after confirmation.')
    current = all_profiles()
    st.metric('Currently saved profiles', len(current))
    if current.empty:
        st.info('No saved profiles.')
    else:
        record_id = st.selectbox('Select one profile to delete', current.id, key='delete_profile_id',
            format_func=lambda x: f"{current.set_index('id').loc[x, 'full_name']} — {current.set_index('id').loc[x, 'linkedin_url']}")
        confirm_profile = st.checkbox('I understand this permanently deletes the selected profile and its scores.', key='confirm_profile_delete')
        if st.button('Delete selected profile', disabled=not confirm_profile or active is not None):
            delete_profile(int(record_id))
            st.success('Profile deleted.')
            st.rerun()
    st.divider()
    st.subheader('Research results')
    with connection() as conn:
        managed_queries = [r[0] for r in conn.execute('SELECT DISTINCT research_query FROM relevance ORDER BY created_at DESC').fetchall()]
    if managed_queries:
        remove_query = st.selectbox('Research query to delete', managed_queries, key='remove_query')
        confirm_query = st.checkbox('I understand this deletes the selected query’s scores and shortlist.', key='confirm_query_delete')
        if st.button('Delete selected research results', disabled=not confirm_query or active is not None):
            delete_research_query(remove_query)
            st.success('Research results deleted.')
            st.rerun()
    else:
        st.info('No saved research queries.')
    st.divider()
    st.subheader('Generated export files')
    files = generated_exports()
    if files:
        export_file = st.selectbox('Generated export file to delete', files, format_func=lambda p: p.name, key='remove_export')
        confirm_export = st.checkbox('I understand this permanently deletes the selected export file.', key='confirm_export_delete')
        if st.button('Delete selected export file', disabled=not confirm_export):
            export_file.unlink()
            st.success('Export file deleted.')
            st.rerun()
    else:
        st.info('No generated export files.')
    st.divider()
    st.subheader('Start completely fresh')
    confirm_all = st.checkbox('I understand this permanently deletes every saved profile, score, and run history.', key='confirm_all_delete')
    if st.button('Clear all database data', type='secondary', disabled=not confirm_all or active is not None):
        replace_dataset()
        st.success('All database data deleted. Import a CSV to begin again.')
        st.rerun()
