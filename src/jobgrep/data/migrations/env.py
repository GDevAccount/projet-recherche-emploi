"""Environnement Alembic.

L'application passe sa propre connexion (Database.migrate). La commande alembic, elle, n'en a pas :
la base visée est alors celle des réglages (DATA_DIR), comme pour l'application.
"""

from alembic import context
from alembic.operations.ops import AlterColumnOp, ModifyTableOps

from jobgrep.data.models import Base

target_metadata = Base.metadata


def _is_primary_key_nullability(operation) -> bool:
    if not isinstance(operation, AlterColumnOp) or operation.modify_nullable is None:
        return False
    column = target_metadata.tables[operation.table_name].columns[operation.column_name]
    return column.primary_key and operation.modify_type is None and operation.modify_server_default is False


def drop_spurious_changes(migration_context, revision, directives) -> None:
    # Les bases d'avant Alembic déclarent « id INTEGER PRIMARY KEY » sans NOT NULL. SQLite n'y met jamais de NULL,
    # mais --autogenerate y verrait une colonne à corriger, et recréerait la table pour rien.
    for script in directives:
        for operations in (script.upgrade_ops, script.downgrade_ops):
            for table_operations in operations.ops:
                if isinstance(table_operations, ModifyTableOps):
                    table_operations.ops = [
                        operation for operation in table_operations.ops if not _is_primary_key_nullability(operation)
                    ]
            operations.ops = [
                operation
                for operation in operations.ops
                if not (isinstance(operation, ModifyTableOps) and not operation.ops)
            ]


def run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite ne sait pas modifier une colonne : Alembic recrée alors la table et recopie ses lignes
        render_as_batch=True,
        process_revision_directives=drop_spurious_changes,
    )
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    run_migrations(connection)
else:
    from dotenv import load_dotenv

    from jobgrep.config import Settings
    from jobgrep.data.database import Database

    load_dotenv()
    with Database(Settings().db_path).engine.begin() as connection:
        run_migrations(connection)
