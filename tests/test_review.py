

def test_add_skips_a_document_already_answered(tmp_path, monkeypatch):
    """The queue id is the document's content hash, so an answer under it never expires."""
    from bankcredit import review
    monkeypatch.setattr(review, "QUEUE", tmp_path / "queue.json")
    monkeypatch.setattr(review, "RESOLVED", tmp_path / "resolved")
    review.RESOLVED.mkdir()

    item = {"id": "abc123", "entity_id": "somebank", "url": "https://x/y.pdf", "reason": "no KM1"}
    assert review.add(item) is True
    assert review.add(item) is False, "already queued"

    review.save([])                                     # reviewer answered it and the queue was cleared
    (review.RESOLVED / "abc123.json").write_text('{"id": "abc123", "values": {}}')
    assert review.add(item) is False, "already answered"
    assert review.load() == []

    assert review.add(dict(item, id="def456")) is True, "different bytes, different document"


def test_ingest_skips_an_unreadable_answer(tmp_path, monkeypatch):
    """One half-written file must not stop every later answer from loading."""
    from bankcredit import review
    monkeypatch.setattr(review, "QUEUE", tmp_path / "queue.json")
    monkeypatch.setattr(review, "RESOLVED", tmp_path / "resolved")
    review.RESOLVED.mkdir()
    (review.RESOLVED / "aaa.json").write_text("")                 # zeroed by a crashed writer
    (review.RESOLVED / "bbb.json").write_text('{"id": "bbb", "skip": true}')
    review.save([{"id": "bbb", "entity_id": "somebank", "status": "open"}])

    review.ingest()                                               # must not raise
    assert review.load() == [], "the readable answer still closed its item"
