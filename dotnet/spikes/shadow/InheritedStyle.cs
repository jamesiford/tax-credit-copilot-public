using System.Diagnostics.CodeAnalysis;

[assembly: SuppressMessage("Style", "IDE0011:Add braces",
    Scope = "namespaceanddescendants", Target = "~N:PlatformSpike",
    Justification = "Compile-linked, unmodified producer input uses its original style gate; shadow code retains the strict gate.")]
