"""
Torna audit_logs imutável no nível do banco de dados (PostgreSQL).

Mesmo que alguém tente UPDATE/DELETE/TRUNCATE diretamente via SQL com o
usuário da aplicação, o trigger impede. Somente um DBA, desabilitando o
trigger conscientemente (ALTER TABLE ... DISABLE TRIGGER), conseguiria
alterar o histórico — e isso fica registrado nos logs do PostgreSQL.
"""
from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION sist_audit_logs_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs é imutável: operação % não permitida', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_logs_no_update_delete ON audit_logs;
CREATE TRIGGER trg_audit_logs_no_update_delete
    BEFORE UPDATE OR DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION sist_audit_logs_immutable();

DROP TRIGGER IF EXISTS trg_audit_logs_no_truncate ON audit_logs;
CREATE TRIGGER trg_audit_logs_no_truncate
    BEFORE TRUNCATE ON audit_logs
    FOR EACH STATEMENT EXECUTE FUNCTION sist_audit_logs_immutable();
"""

REVERSE = """
DROP TRIGGER IF EXISTS trg_audit_logs_no_update_delete ON audit_logs;
DROP TRIGGER IF EXISTS trg_audit_logs_no_truncate ON audit_logs;
DROP FUNCTION IF EXISTS sist_audit_logs_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
