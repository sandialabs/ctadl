# SQL queries for inspecting the database

## Get the assignments in a function with variable names

```sql
SELECT
    n1.name AS dst, si1.value AS dstname, p1 AS dstp, n2.name AS src, si2.value AS srcname, p2 AS srcp
FROM VirtualAssign va
JOIN IntCInsn_InFunction iif USING (insn)
JOIN CVar_Name n1 ON (n1.var = v1)
JOIN CVar_Name n2 ON (n2.var = v2)
-- join to get the name of the variable. the nested select is crucial
LEFT JOIN
    (SELECT * FROM CVar_SourceInfo WHERE key = 'name') si1
    ON (va.v1 = si1.var)
LEFT JOIN
    (SELECT * FROM CVar_SourceInfo WHERE key = 'name') si2
    ON (va.v2 = si2.var)
-- Function whose assigns you want
WHERE iif."function" = 'THEFUNCTION'
ORDER BY iif."function", iif."index"
```

```
(SELECT insn, "to" AS v1, "to_path" AS p1, "from" AS v2, "from_path" AS p2, "move" AS reason FROM CInsn_Move)
```
CInsn_Move: v1 -> to, p1 -> to_path, v2 -> from, p2 -> from_path

## All the callsites with arguments and callees, grouped

```sql
SELECT
    insn,
    GROUP_CONCAT(('[' || act."index" || '] ' || act.param || act.ap), char(10)) AS actualv,
    GROUP_CONCAT(ce.function,char(10)) AS callees
FROM CCall_ActualParam act
JOIN IntCInsn_InFunction iif USING (insn)
LEFT OUTER JOIN CallEdge ce USING (insn)
WHERE
  -- Function whose call instructions you want
  iif.function = 'THEFUNCTION'
  AND act."index" >= 0
GROUP BY insn
ORDER BY insn, act."index"
```

## Summary entries grouped by from,to

```sql
SELECT
    m1, n1, name1.name, p1, n2, name2.name, p2, ctx
FROM SummaryFlow
JOIN
    CFunction_FormalParam param1 ON (
        param1.function = m1 AND param1."index" = n1
    )
JOIN CVar_Name name1 ON (param1.param = name1.var)
JOIN
    CFunction_FormalParam param2 ON (
        param2.function = m1 AND param2."index" = n2
    )
JOIN CVar_Name name2 ON (param2.param = name2.var)
WHERE m1 = 'THEFUNCTION'
ORDER BY m1, n1, n2
```

## Tainted variables and instructions

```sql
SELECT
    rv.v1,
    si.value,
    GROUP_CONCAT(p1, char(10)) AS "path",
    rv.direction
FROM (SELECT DISTINCT v1, p1, direction FROM 'flow.ReachableVertex') rv
JOIN CVar_Name n1 ON (n1.var = v1)
LEFT JOIN
    (SELECT * FROM CVar_SourceInfo WHERE key = 'name') si
    ON (rv.v1 = si.var)
GROUP BY rv.v1, rv.p1
ORDER BY rv.v1, rv.p1
```

```sql
SELECT
    --re.insn,
    dstn.var AS dst_var,
    dstsi.value AS dst_name,
    dst.p1,
    srcn.var AS src_var,
    srcsi.value AS src_name,
    src.p1,
    re.direction
FROM 'natural_flow.ReachableEdge' re
JOIN
    'flow.ReachableVertex' dst ON (
        re.vertex_to = dst.id
        AND re.direction = dst.direction
    )
JOIN
    'flow.ReachableVertex' src ON (
        re.vertex_from = src.id
        AND re.direction = src.direction
    )
JOIN CVar_Name dstn ON (dstn.var = dst.v1)
JOIN CVar_Name srcn ON (srcn.var = src.v1)
LEFT JOIN
    (SELECT * FROM CVar_SourceInfo WHERE key = 'name') dstsi
    ON (dst.v1 = dstsi.var)
LEFT JOIN
    (SELECT * FROM CVar_SourceInfo WHERE key = 'name') srcsi
    ON (src.v1 = srcsi.var)
ORDER BY re.insn
```


## PCODE

```sql
SELECT
    printf("%x", target.target_address) AS addr,
    o.vnode_id AS output,
    mnem.mnemonic,
    i0.vnode_id AS in0,
    i1.vnode_id AS in1,
    i2.vnode_id AS in2
FROM PCODE_INDEX idx
JOIN PCODE_MNEMONIC mnem USING (id)
JOIN PCODE_TARGET target USING (id)
JOIN PCODE_PARENT par USING (id)
JOIN BB_HFUNC bbf USING (bbid)
LEFT JOIN PCODE_OUTPUT o USING (id)
JOIN PCODE_INPUT i0 ON (i0.id=idx.id AND i0.i=0)
LEFT JOIN PCODE_INPUT i1 ON (i1.id=idx.id AND i1.i=1)
LEFT JOIN PCODE_INPUT i2 ON (i2.id=idx.id AND i2.i=2)
WHERE
-- Function to fetch
bbf.hfunc = 'main@1400014d2'
ORDER BY target.target_address, idx."index"
```


### Indexes

```sql
CREATE INDEX idx_PCODE_TOSTR_0 ON _PCODE_TOSTR ("0");
CREATE INDEX idx_PCODE_MNEMONIC_0 ON _PCODE_MNEMONIC ("0");
CREATE INDEX idx_PCODE_OPCODE_0 ON _PCODE_OPCODE ("0");
CREATE INDEX idx_PCODE_PARENT_0 ON _PCODE_PARENT ("0");
CREATE INDEX idx_PCODE_TARGET_0 ON _PCODE_TARGET ("0");
CREATE INDEX idx_PCODE_INPUT_COUNT_0 ON _PCODE_INPUT_COUNT ("0");
CREATE INDEX idx_PCODE_INPUT_0 ON _PCODE_INPUT ("0");
CREATE INDEX idx_PCODE_OUTPUT_0 ON _PCODE_OUTPUT ("0");
CREATE INDEX idx_PCODE_NEXT_0 ON _PCODE_NEXT ("0");
CREATE INDEX idx_PCODE_TIME_0 ON _PCODE_TIME ("0");
CREATE INDEX idx_PCODE_INDEX_0 ON _PCODE_INDEX ("0");
CREATE INDEX idx_VNODE_ADDRESS_0 ON _VNODE_ADDRESS ("0");
CREATE INDEX idx_VNODE_IS_ADDRESS_0 ON _VNODE_IS_ADDRESS ("0");
CREATE INDEX idx_VNODE_IS_ADDRTIED_0 ON _VNODE_IS_ADDRTIED ("0");
CREATE INDEX idx_VNODE_PC_ADDRESS_0 ON _VNODE_PC_ADDRESS ("0");
CREATE INDEX idx_VNODE_DESC_0 ON _VNODE_DESC ("0");
CREATE INDEX idx_VNODE_NAME_0 ON _VNODE_NAME ("0");
CREATE INDEX idx_VNODE_OFFSET_0 ON _VNODE_OFFSET ("0");
CREATE INDEX idx_VNODE_OFFSET_N_0 ON _VNODE_OFFSET_N ("0");
CREATE INDEX idx_VNODE_SIZE_0 ON _VNODE_SIZE ("0");
CREATE INDEX idx_VNODE_SPACE_0 ON _VNODE_SPACE ("0");
CREATE INDEX idx_VNODE_TOSTR_0 ON _VNODE_TOSTR ("0");
CREATE INDEX idx_VNODE_HVAR_0 ON _VNODE_HVAR ("0");
CREATE INDEX idx_VNODE_HFUNC_0 ON _VNODE_HFUNC ("0");
CREATE INDEX idx_VNODE_DEF_0 ON _VNODE_DEF ("0");
```
