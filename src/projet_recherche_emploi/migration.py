import sqlite3

# Les lignes créées avant les comptes appartiennent à cet utilisateur
DEFAULT_USER_ID = 1

def add_user_id(connection: sqlite3.Connection, table: str, create_statement: str) -> bool:
    """Rattache une table d'avant les comptes à l'utilisateur par défaut, et renvoie vrai si elle a été migrée.

    SQLite ne sait pas changer une clé primaire ou une contrainte d'unicité : la table est
    recréée avec create_statement, puis ses lignes sont recopiées.
    """
    if _has_user_id(connection, table):
        return False

    # Python n'ouvre pas de transaction pour un ALTER ou un CREATE : sans ce BEGIN,
    # une erreur en cours de route laisserait la table à moitié migrée.
    # IMMEDIATE fait attendre une autre session qui lancerait la même migration.
    if not connection.in_transaction:
        connection.execute("BEGIN IMMEDIATE")
    if _has_user_id(connection, table):
        return False

    old_table = f"{table}_old"
    old_columns = ", ".join(row[1] for row in connection.execute(f"PRAGMA table_info({table})"))
    connection.execute(f"ALTER TABLE {table} RENAME TO {old_table}")
    connection.execute(create_statement)
    # user_id n'est pas dans la liste : il prend sa valeur par défaut
    connection.execute(f"INSERT INTO {table} ({old_columns}) SELECT {old_columns} FROM {old_table}")

    old_count = connection.execute(f"SELECT COUNT(*) FROM {old_table}").fetchone()[0]
    new_count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    if new_count != old_count:
        raise RuntimeError(f"Migration de {table} annulée : {new_count} ligne(s) recopiée(s) sur {old_count}")

    connection.execute(f"DROP TABLE {old_table}")
    return True


def _has_user_id(connection: sqlite3.Connection, table: str) -> bool:
    return any(row[1] == "user_id" for row in connection.execute(f"PRAGMA table_info({table})"))
