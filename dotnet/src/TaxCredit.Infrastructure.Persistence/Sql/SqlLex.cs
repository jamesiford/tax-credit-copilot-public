namespace TaxCredit.Infrastructure.Persistence.Sql;

internal static class SqlLex
{
    internal static string Mask(string sql)
    {
        var chars = sql.ToCharArray();
        for (var i = 0; i < sql.Length; i++)
        {
            if (sql[i] is '\'' or '"' or '[')
            {
                var close = sql[i] == '[' ? ']' : sql[i];
                chars[i] = ' ';
                var closed = false;
                while (++i < sql.Length)
                {
                    chars[i] = ' ';
                    if (sql[i] != close)
                    {
                        continue;
                    }

                    if (i + 1 < sql.Length && sql[i + 1] == close)
                    {
                        chars[++i] = ' ';
                        continue;
                    }

                    closed = true;
                    break;
                }

                if (!closed)
                {
                    throw new TenantScopeViolation("Unterminated SQL literal or identifier.");
                }
            }
            else if (i + 1 < sql.Length && sql[i] == '-' && sql[i + 1] == '-')
            {
                while (i < sql.Length && sql[i] != '\n')
                {
                    chars[i++] = ' ';
                }
            }
            else if (i + 1 < sql.Length && sql[i] == '/' && sql[i + 1] == '*')
            {
                var end = sql.IndexOf("*/", i + 2, StringComparison.Ordinal);
                if (end < 0)
                {
                    throw new TenantScopeViolation("Unterminated SQL comment.");
                }

                while (i <= end + 1)
                {
                    chars[i++] = ' ';
                }

                i--;
            }
        }

        return new string(chars);
    }

    internal static BoundStatement NameParameters(BoundStatement statement)
    {
        var mask = Mask(statement.Sql);
        var index = 0;
        var output = new System.Text.StringBuilder();
        for (var i = 0; i < mask.Length; i++)
        {
            if (mask[i] == '?')
            {
                output.Append("@p").Append(index++);
            }
            else
            {
                output.Append(statement.Sql[i]);
            }
        }

        if (index != statement.Values.Count)
        {
            throw new TenantScopeViolation("Incorrect parameter count.");
        }

        return statement with { Sql = output.ToString() };
    }
}
