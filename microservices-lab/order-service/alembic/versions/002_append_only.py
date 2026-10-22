"""Bloquear UPDATE/DELETE/TRUNCATE y dar permisos mínimos a order_app."""
from alembic import op
revision='002_append_only'
down_revision='001_eventstore'
branch_labels=None
depends_on=None

def upgrade():
    op.execute("""CREATE FUNCTION prevent_event_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'events is append-only: % is forbidden',TG_OP; END; $$""")
    op.execute("""CREATE TRIGGER events_immutable_rows BEFORE UPDATE OR DELETE ON events
        FOR EACH ROW EXECUTE FUNCTION prevent_event_mutation()""")
    op.execute("""CREATE TRIGGER events_immutable_truncate BEFORE TRUNCATE ON events
        FOR EACH STATEMENT EXECUTE FUNCTION prevent_event_mutation()""")
    op.execute('REVOKE ALL ON events FROM PUBLIC')
    op.execute('GRANT SELECT,INSERT ON events TO order_app')
    op.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON order_projections,snapshot_orders,outbox TO order_app')
    op.execute('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO order_app')
    op.execute('GRANT USAGE ON SCHEMA public TO order_app')

def downgrade():
    op.execute('DROP TRIGGER events_immutable_rows ON events')
    op.execute('DROP TRIGGER events_immutable_truncate ON events')
    op.execute('DROP FUNCTION prevent_event_mutation()')
