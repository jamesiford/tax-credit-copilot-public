/* ============================================================================
   0002 — who set a programme engagement

   PUT /api/claims/engagement recorded no actor and tcc_ops.program_engagement had
   no column to hold one. Both columns are nullable, so existing rows stay valid
   (their author is genuinely unknown) and ALTER TABLE ... ADD is supported by the
   Fabric Warehouse for a nullable column.
   ============================================================================ */

ALTER TABLE tcc_ops.program_engagement ADD set_by VARCHAR(256) NULL;
GO

ALTER TABLE tcc_ops.program_engagement ADD set_at DATETIME2(3) NULL;
GO
