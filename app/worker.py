"""Background scoring worker launched by the Streamlit UI."""
import sys
from .database import update_run, log, connection
from .scoring import score_profiles


def main(run_id, query):
    with connection() as conn:
        total = conn.execute('SELECT total FROM runs WHERE id=?', (run_id,)).fetchone()[0]
    log(run_id, 'INFO', f'Background scoring worker started for {total} profiles.')
    try:
        completed = score_profiles(query, run_id=run_id)
        with connection() as conn:
            run = conn.execute('SELECT status FROM runs WHERE id=?', (run_id,)).fetchone()
        if run and run['status'] == 'Stopped':
            log(run_id, 'INFO', f'Job stopped after {completed} profiles.')
        else:
            update_run(run_id, status='Completed', processed=completed, succeeded=completed,
                       message='CSV-first research matching completed')
            log(run_id, 'INFO', f'Scored {completed} profiles.')
    except Exception as exc:
        update_run(run_id, status='Failed', message=str(exc))
        log(run_id, 'ERROR', str(exc))
        raise


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: python -m app.worker RUN_ID "research keywords"')
    main(int(sys.argv[1]), sys.argv[2])
