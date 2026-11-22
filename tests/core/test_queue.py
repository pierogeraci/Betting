from sqlalchemy import text

from core import queue
from core.models import Lavoro


def _take(db, kinds=("snapshot",), worker="w1"):
    return (
        db.execute(text("select * from lavoro_prendi(:k, :w, 60)"), {"k": list(kinds), "w": worker})
        .mappings()
        .first()
    )


def _close(db, job_id, ok, worker="w1", error=None):
    return db.execute(
        text("select lavoro_chiudi(:i, :w, :ok, cast(:r as jsonb), :e)"),
        {"i": job_id, "w": worker, "ok": ok, "r": '{"esito": "riuscito"}', "e": error},
    ).scalar()


def test_collect_cycle_creates_followup(db):
    job = queue.enqueue(
        db,
        queue=queue.COLLECT,
        kind="snapshot",
        payload={"url": "https://a.example.com/"},
        next_kind="acquisisci_snapshot",
    )
    taken = _take(db)
    assert taken["id"] == job.id and taken["carico"]["url"].startswith("https://")
    assert _take(db) is None  # già preso
    assert _close(db, job.id, True, worker="altro") is False  # solo chi l'ha preso può chiuderlo
    assert _close(db, job.id, True) is True
    db.refresh(job)
    assert job.stato == "completato"
    follow = db.query(Lavoro).filter(Lavoro.origine_id == job.id).one()
    assert (follow.coda, follow.tipo, follow.carico) == (
        "interna",
        "acquisisci_snapshot",
        {"lavoro_origine": job.id},
    )


def test_collect_failure_retries_then_fails(db):
    job = queue.enqueue(db, queue=queue.COLLECT, kind="snapshot", max_attempts=2)
    _take(db)
    _close(db, job.id, False, error="primo errore")
    db.refresh(job)
    assert job.stato == "in_attesa"
    db.execute(
        text("update lavoro set disponibile_dal = now() - interval '1 minute' where id = :i"), {"i": job.id}
    )
    _take(db)
    _close(db, job.id, False, error="secondo errore")
    db.refresh(job)
    assert job.stato == "fallito" and job.errore == "secondo errore"


def test_collect_role_cannot_take_internal_jobs(db):
    queue.enqueue(db, queue=queue.INTERNAL, kind="snapshot")
    assert _take(db) is None


def test_collect_role_has_no_table_access(db):
    tables = db.execute(
        text("select count(*) from information_schema.role_table_grants where grantee = 'raccolta'")
    ).scalar()
    assert tables == 0
    assert db.execute(
        text("select has_function_privilege('raccolta', 'lavoro_prendi(text[], text, integer)', 'execute')")
    ).scalar()
    assert not db.execute(text("select has_table_privilege('raccolta', 'lavoro', 'select')")).scalar()
    assert not db.execute(text("select has_table_privilege('raccolta', 'utente', 'select')")).scalar()


def test_internal_claim_complete_fail(db):
    a = queue.enqueue(db, queue=queue.INTERNAL, kind="confronto_adm")
    job = queue.claim_internal(db, "lav")
    assert job.id == a.id and job.stato == "in_corso"
    queue.fail(db, job, "errore")
    assert job.stato == "in_attesa"
    assert queue.claim_internal(db, "lav") is None  # non ancora disponibile: attesa prima del nuovo tentativo
    again = queue.retry(db, job)
    assert again.origine_id == job.id and again.stato == "in_attesa"
