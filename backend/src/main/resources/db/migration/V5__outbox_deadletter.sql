-- Dead-letter support for the outbox relay: a row that can't be published (unparseable payload, or a
-- send that fails past the retry cap) is parked here instead of blocking every later event forever.
ALTER TABLE outbox_event ADD COLUMN dead_lettered_at   TIMESTAMPTZ;
ALTER TABLE outbox_event ADD COLUMN dead_letter_reason VARCHAR(512);

-- The relay scans for rows that are unpublished AND not dead-lettered; index that predicate.
DROP INDEX IF EXISTS ix_outbox_unpublished;
CREATE INDEX ix_outbox_pending ON outbox_event (published_at, dead_lettered_at, id);
