# Transactional load failure

Version: 1
Stage: load

SQLite rejected an operation. The generic error does not identify whether permissions, a lock, or a schema conflict caused it.

Check write access, concurrent writers and table compatibility. Verify the stored count before retrying.
