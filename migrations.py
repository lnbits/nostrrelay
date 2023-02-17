async def m001_initial(db):
    """
    Initial nostrrelays tables.
    """

    await db.execute(
        """
        CREATE TABLE nostrrelay.relays (
            user_id TEXT NOT NULL,
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            pubkey TEXT,
            contact TEXT,
            active BOOLEAN DEFAULT false,
            meta TEXT NOT NULL DEFAULT '{}'
        );
        """
    )

    await db.execute(
        f"""
        CREATE TABLE nostrrelay.events (
            relay_id TEXT NOT NULL,
            deleted BOOLEAN DEFAULT false,
            publisher TEXT NOT NULL,
            id TEXT NOT NULL,
            pubkey TEXT NOT NULL,
            created_at {db.big_int} NOT NULL,
            kind INT NOT NULL,
            content TEXT NOT NULL,
            sig TEXT NOT NULL,
            size {db.big_int} DEFAULT 0,
            PRIMARY KEY (relay_id, id)
        );
        """
    )

    await db.execute(
        """
        CREATE TABLE nostrrelay.event_tags (
            relay_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            name TEXT NOT NULL,
            value TEXT NOT NULL,
            extra TEXT
        );
        """
    )

    await db.execute(
        f"""
        CREATE TABLE nostrrelay.accounts (
            relay_id TEXT NOT NULL,
            pubkey TEXT NOT NULL,
            sats {db.big_int} DEFAULT 0,
            storage {db.big_int} DEFAULT 0,
            paid_to_join BOOLEAN DEFAULT false,
            allowed BOOLEAN DEFAULT false,
            blocked BOOLEAN DEFAULT false,
            PRIMARY KEY (relay_id, pubkey)
        );
        """
    )
