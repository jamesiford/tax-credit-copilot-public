"""The infrastructure layer: adapters that implement domain ports. [ADR-002]

Everything that talks to a database, a file system, or a network lives here.
`import sqlite3` and `import pyodbc` appear in this package and nowhere
else in the codebase.
"""
