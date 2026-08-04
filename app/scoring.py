import re
import time
from collections import Counter
from math import log, sqrt
from .database import connection, utcnow

# Canonical research areas get conservative, explainable title/domain variants.
# They are designed for the limited Company + Position data in a Connections CSV.
AREA_ALIASES = {
    'devsecops': ('devsecops', 'devops', 'dev ops', 'cloud security', 'application security', 'appsec', 'ci/cd', 'devsec'),
    'secure scrum': ('secure scrum', 'scrum master', 'scrum', 'agile coach', 'agile delivery', 'safe agile'),
    'software architecture': ('software architecture', 'software architect', 'solution architect', 'solutions architect',
                              'enterprise architect', 'technical architect', 'system architect', 'architect', 'architecture',
                              'system design', 'technical lead', 'engineering lead'),
    'cybersecurity': ('cybersecurity', 'cyber security', 'information security', 'infosec', 'security engineer', 'security analyst'),
}


def keywords(query):
    return [item.strip().lower() for item in re.split(r'[,;\n]+', query) if item.strip()]


def aliases_for(area):
    return AREA_ALIASES.get(area, (area,))


def tokens(text):
    words = re.findall(r'[a-z0-9+#.-]+', text.lower())
    return words + [' '.join(words[i:i+2]) for i in range(len(words)-1)]


def tfidf_vector(terms, document_frequency, total_documents):
    counts = Counter(terms)
    return {term: count * (log((total_documents + 1) / (document_frequency[term] + 1)) + 1)
            for term, count in counts.items()}


def cosine(vector_a, vector_b):
    numerator = sum(vector_a[term] * vector_b.get(term, 0) for term in vector_a)
    denominator = sqrt(sum(x*x for x in vector_a.values())) * sqrt(sum(x*x for x in vector_b.values()))
    return numerator / denominator if denominator else 0.0


def cosine_tfidf(text, query, documents):
    """Compatibility helper for small tests and one-off calls."""
    query_terms, text_terms = tokens(query), tokens(text)
    if not query_terms or not text_terms: return 0.0
    document_frequency = Counter(term for document in documents for term in set(tokens(document)))
    return cosine(tfidf_vector(text_terms, document_frequency, len(documents) + 1),
                  tfidf_vector(query_terms, document_frequency, len(documents) + 1))


def classify(text, years, score):
    words = text.lower()
    academic = bool(re.search(r'\b(professor|lecturer|researcher|phd|university|academic)\b', words))
    industry = bool(re.search(r'\b(engineer|architect|manager|director|consultant|developer|lead)\b', words))
    security = bool(re.search(r'\b(security|cyber|devsecops|infosec|application security)\b', words))
    architecture = bool(re.search(r'\b(architect|architecture|solution design|enterprise design)\b', words))
    validator = (years or 0) >= 5 and score >= 70 and (academic or industry)
    priority = 'High' if validator and score >= 85 and (years or 0) >= 8 else 'Medium' if validator else 'Low'
    return academic, industry, security, architecture, validator, priority


def score_profiles(query, progress_callback=None, run_id=None):
    terms = keywords(query)
    if not terms: raise ValueError('Enter at least one keyword or research area.')
    with connection() as conn:
        profiles = conn.execute('SELECT * FROM profiles').fetchall()
    if run_id:
        with connection() as conn:
            status = conn.execute('SELECT status FROM runs WHERE id=?', (run_id,)).fetchone()['status']
            if status == 'Stop requested':
                conn.execute("UPDATE runs SET status='Stopped', message='Stopped by user before processing', updated_at=? WHERE id=?", (utcnow(), run_id))
                return 0
    texts = []
    for row in profiles:
        texts.append(' '.join(str(row[k] or '') for k in ('headline','current_position','current_company','about','skills','imported_position','imported_company')))
    if not profiles: return 0
    # Build the corpus statistics once. The previous implementation rebuilt
    # these thousands of times, making a 2,500-profile run needlessly slow.
    tokenised_texts = [tokens(text) for text in texts]
    document_frequency = Counter(term for item in tokenised_texts for term in set(item))
    term_vectors = [tfidf_vector(tokens(term), document_frequency, len(texts) + 1) for term in terms]
    text_vectors = [tfidf_vector(item, document_frequency, len(texts) + 1) for item in tokenised_texts]
    now = utcnow()
    with connection() as conn:
        for index, row in enumerate(profiles):
            text = texts[index].lower()
            matched = []
            area_strength = []
            for area in terms:
                aliases = aliases_for(area)
                hits = [alias for alias in aliases if alias in text]
                if hits:
                    # A direct requested phrase is strongest; associated terms
                    # are deliberately lower but still research-relevant.
                    strength = 0.95 if area in hits else min(0.82, 0.65 + 0.08 * (len(hits) - 1))
                    area_strength.append((area, strength))
                    matched.extend(hits)
            per_area = [cosine(text_vectors[index], vector) for vector in term_vectors]
            semantic = max(per_area) if per_area else 0
            lexical = max((strength for _, strength in area_strength), default=0)
            score = round(min(100, lexical * 78 + semantic * 35 + min(8, max(0, len(set(matched)) - 1) * 3)), 1)
            area = ', '.join(area for area, _ in area_strength) if area_strength else (terms[per_area.index(max(per_area))] if semantic >= .18 else 'Not identified')
            confidence = 'High' if score >= 70 else 'Medium' if score >= 40 else 'Low'
            flags = classify(text, row['total_experience_years'], score)
            conn.execute("""INSERT INTO relevance(profile_id,research_query,research_area,matched_keywords,relevance_score,relevant_flag,
              confidence,academic_expert,industry_expert,security_expert,architecture_expert,potential_validator,validation_priority,created_at)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(profile_id,research_query) DO UPDATE SET
              research_area=excluded.research_area,matched_keywords=excluded.matched_keywords,relevance_score=excluded.relevance_score,
              relevant_flag=excluded.relevant_flag,confidence=excluded.confidence,academic_expert=excluded.academic_expert,
              industry_expert=excluded.industry_expert,security_expert=excluded.security_expert,architecture_expert=excluded.architecture_expert,
              potential_validator=excluded.potential_validator,validation_priority=excluded.validation_priority,created_at=excluded.created_at""",
              (row['id'],query,area,', '.join(dict.fromkeys(matched)),score,'Yes' if score >= 50 else 'No',confidence,
               *('Yes' if value else 'No' for value in flags[:5]),flags[5],now))
            if progress_callback and ((index + 1) % 25 == 0 or index + 1 == len(profiles)):
                # Release the scoring write transaction before the UI updates
                # the separate run-progress record.
                conn.commit()
                progress_callback(index + 1, len(profiles), row['full_name'])
            if run_id and ((index + 1) % 25 == 0 or index + 1 == len(profiles)):
                conn.execute("UPDATE runs SET processed=?, succeeded=?, current_item=?, updated_at=? WHERE id=?",
                             (index + 1, index + 1, row['full_name'], utcnow(), run_id))
                if (index + 1) % 250 == 0:
                    conn.execute("INSERT INTO events(run_id,level,message,created_at) VALUES (?,?,?,?)",
                                 (run_id, 'INFO', f'Progress: {index + 1} of {len(profiles)} profiles scored.', utcnow()))
                conn.commit()
                while True:
                    status = conn.execute('SELECT status FROM runs WHERE id=?', (run_id,)).fetchone()['status']
                    if status == 'Stop requested':
                        conn.execute("UPDATE runs SET status='Stopped', message='Stopped by user', updated_at=? WHERE id=?", (utcnow(), run_id))
                        conn.commit()
                        return index + 1
                    if status != 'Paused':
                        break
                    time.sleep(0.5)
    return len(profiles)
