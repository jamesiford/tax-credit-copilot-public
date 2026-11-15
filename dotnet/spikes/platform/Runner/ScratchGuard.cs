using Microsoft.SqlServer.TransactSql.ScriptDom;

namespace PlatformSpike;

internal sealed class ScratchGuard(string sourceSchema, IEnumerable<string> sourceTables)
{
    internal const string Schema = "tcc_scratch_dotnet";
    private readonly HashSet<string> sources = new(sourceTables.Select(t => $"{sourceSchema}.{t}"),
        StringComparer.OrdinalIgnoreCase);
    private static readonly HashSet<string> Metadata = new(StringComparer.OrdinalIgnoreCase)
    {
        "INFORMATION_SCHEMA.COLUMNS", "INFORMATION_SCHEMA.TABLES",
        "sys.objects", "sys.schemas", "sys.tables", "sys.columns", "sys.types"
    };

    internal void Check(string sql)
    {
        // Reject batches and comments outright rather than trying to de-obfuscate them.
        if (sql.Contains(';', StringComparison.Ordinal) || sql.Contains("--", StringComparison.Ordinal)
            || sql.Contains("/*", StringComparison.Ordinal) || sql.Contains("*/", StringComparison.Ordinal))
            throw new GuardRefusal("Batches and comments are forbidden.");
        var parser = new TSql170Parser(true);
        var tree = parser.Parse(new StringReader(sql), out var errors);
        if (errors.Count != 0 || tree is not TSqlScript { Batches.Count: 1 } script
            || script.Batches[0].Statements.Count != 1)
            throw new GuardRefusal("Exactly one valid T-SQL statement is required.");
        var statement = script.Batches[0].Statements[0];
        switch (statement)
        {
            case SelectStatement select when select.Into is null:
                break;
            case InsertStatement insert:
                RequireNamedTarget(insert.InsertSpecification.Target);
                if (insert.InsertSpecification.OutputClause is not null
                    || insert.InsertSpecification.OutputIntoClause is not null)
                    throw new GuardRefusal("OUTPUT is forbidden.");
                break;
            case UpdateStatement update:
                RequireNamedTarget(update.UpdateSpecification.Target);
                if (update.UpdateSpecification.OutputClause is not null
                    || update.UpdateSpecification.OutputIntoClause is not null)
                    throw new GuardRefusal("OUTPUT is forbidden.");
                break;
            case DeleteStatement delete:
                RequireNamedTarget(delete.DeleteSpecification.Target);
                if (delete.DeleteSpecification.OutputClause is not null
                    || delete.DeleteSpecification.OutputIntoClause is not null)
                    throw new GuardRefusal("OUTPUT is forbidden.");
                break;
            case CreateTableStatement create:
                RequireScratch(create.SchemaObjectName);
                break;
            case DropTableStatement drop:
                foreach (var table in drop.Objects) RequireScratch(table);
                break;
            case CreateSchemaStatement createSchema when
                createSchema.Name.Value.Equals(Schema, StringComparison.OrdinalIgnoreCase)
                && (createSchema.StatementList is null || createSchema.StatementList.Statements.Count == 0)
                && createSchema.Owner is null:
                break;
            case DropSchemaStatement dropSchema when
                dropSchema.Schema.Identifiers.Count == 1
                && dropSchema.Schema.Identifiers[0].Value.Equals(Schema, StringComparison.OrdinalIgnoreCase):
                break;
            default:
                throw new GuardRefusal("Statement kind is outside the experiment allowlist.");
        }
        var visitor = new References(this, statement is SelectStatement);
        statement.Accept(visitor);
    }

    private static void RequireNamedTarget(TableReference target)
    {
        if (target is not NamedTableReference named)
            throw new GuardRefusal("A write must name a fully qualified scratch table.");
        RequireScratch(named.SchemaObject);
    }

    private static string Qualified(SchemaObjectName name)
    {
        if (name.Identifiers.Count != 2)
            throw new GuardRefusal("Two-part object names only.");
        return $"{name.Identifiers[0].Value}.{name.Identifiers[1].Value}";
    }

    private static void RequireScratch(SchemaObjectName name)
    {
        _ = Qualified(name);
        if (!name.Identifiers[0].Value.Equals(Schema, StringComparison.OrdinalIgnoreCase))
            throw new GuardRefusal("Non-scratch write refused.");
    }

    private sealed class References(ScratchGuard guard, bool readOnly) : TSqlFragmentVisitor
    {
        public override void ExplicitVisit(NamedTableReference node)
        {
            var name = Qualified(node.SchemaObject);
            var scratch = node.SchemaObject.Identifiers[0].Value.Equals(Schema, StringComparison.OrdinalIgnoreCase);
            if (!scratch && !(readOnly && (Metadata.Contains(name) || guard.sources.Contains(name))))
                throw new GuardRefusal("Object is outside the read/write allowlist.");
            base.ExplicitVisit(node);
        }

        public override void ExplicitVisit(SchemaObjectFunctionTableReference node) =>
            throw new GuardRefusal("Table-valued functions are forbidden.");

        public override void ExplicitVisit(OpenRowsetTableReference node) =>
            throw new GuardRefusal("External rowsets are forbidden.");

        public override void ExplicitVisit(FunctionCall node)
        {
            if (node.CallTarget is not null)
                throw new GuardRefusal("User-defined functions are forbidden.");
            base.ExplicitVisit(node);
        }

        public override void ExplicitVisit(SelectSetVariable node) =>
            throw new GuardRefusal("SELECT variable assignment is forbidden.");
    }

    internal static int SelfTest()
    {
        var guard = new ScratchGuard("tcc_source", ["Payroll"]);
        string[] denied =
        [
            "INSERT INTO tcc_gold.employee_period_fact (client_id) VALUES (1)",
            "DROP TABLE tcc_ops.run_manifest",
            "SELECT 1; SELECT 2",
            "INSERT INTO tcc_/*hidden*/gold.example VALUES (1)",
            "INSERT INTO TcC_GoLd.example VALUES (1)",
            "INSERT INTO [tcc_gold].[example] VALUES (1)",
            "DROP TABLE [TcC_OpS].[run_manifest]",
            "DROP TABLE tcc_scratch_dotnet.a, tcc_ops.run_manifest",
            "SELECT * INTO tcc_ops.example FROM tcc_scratch_dotnet.a",
            "UPDATE tcc_gold.example SET client_id = 1",
            "DELETE FROM tcc_source.Payroll",
            "INSERT INTO tcc_scratch_dotnet.a SELECT * FROM tcc_gold.example",
            "SELECT * FROM other_source.Payroll",
            "EXEC ('SELECT 1')",
            "CREATE SCHEMA tcc_ops",
            "CREATE SCHEMA tcc_scratch_dotnet CREATE TABLE tcc_ops.example (id int)",
            "SELECT * FROM [other_database].[tcc_source].[Payroll]",
            "SELECT dbo.dangerous_function()",
            "SELECT * FROM OPENROWSET(BULK 'file', SINGLE_CLOB) AS x",
            "TRUNCATE TABLE tcc_ops.run_manifest"
        ];
        foreach (var sql in denied)
        {
            try { guard.Check(sql); throw new InvalidOperationException("Guard self-test failed."); }
            catch (GuardRefusal) { }
        }
        string[] allowed =
        [
            "SELECT 1",
            "SELECT COUNT(*) FROM tcc_source.Payroll",
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @schema",
            "SELECT COUNT(*) FROM sys.objects o JOIN sys.schemas s ON o.schema_id = s.schema_id",
            "CREATE SCHEMA tcc_scratch_dotnet",
            "CREATE TABLE [tcc_scratch_dotnet].[example] (id int NOT NULL, amount decimal(18,2))",
            "INSERT INTO [TcC_ScRaTcH_DoTnEt].[example] (id) VALUES (@id)",
            "UPDATE tcc_scratch_dotnet.example SET id = @id WHERE id = @old",
            "DELETE FROM tcc_scratch_dotnet.example WHERE id = @id",
            "DROP TABLE tcc_scratch_dotnet.example",
            "DROP SCHEMA tcc_scratch_dotnet"
        ];
        foreach (var sql in allowed) guard.Check(sql);
        Console.WriteLine($"ScratchGuard: {denied.Length} forbidden statements refused; {allowed.Length} allowed statements passed.");
        return denied.Length + allowed.Length;
    }
}

internal sealed class GuardRefusal(string message) : Exception(message);
