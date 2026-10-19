"""Parameterized SQL/Cypher counterparts for the seven project questions."""

SQL = {
"Q1": """SELECT COUNT(*)::bigint AS transfer_count, COALESCE(SUM(amount_rwf),0)::bigint AS total_rwf
FROM transfers WHERE sender_id=%(account)s AND occurred_at >= %(start)s AND occurred_at < %(end)s""",
"Q2": """SELECT (to_timestamp(occurred_at) AT TIME ZONE 'Africa/Kigali')::date AS cat_date,
COUNT(*)::bigint AS transfer_count, SUM(amount_rwf)::bigint AS total_rwf
FROM transfers GROUP BY 1 ORDER BY 1""",
"Q3": """SELECT d2.account_id AS other_account, d1.device_id,
       v.access_type, GREATEST(d1.first_day,d2.first_day)::int AS overlap_start,
       LEAST(d1.last_day,d2.last_day)::int AS overlap_end
FROM account_devices d1
JOIN account_devices d2 ON d1.device_id=d2.device_id AND d1.account_id<>d2.account_id
JOIN devices v ON v.device_id=d1.device_id
WHERE d1.account_id=%(account)s
  AND GREATEST(d1.first_day,d2.first_day)<=LEAST(d1.last_day,d2.last_day)
ORDER BY 1,2""",
"Q4": """WITH RECURSIVE edges(sk,si,dk,di) AS (
 SELECT 'Customer',customer_id,'Account',account_id FROM accounts
 UNION ALL SELECT 'Account',account_id,'Customer',customer_id FROM accounts
 UNION ALL SELECT 'Account',account_id,'Device',device_id FROM account_devices
 UNION ALL SELECT 'Device',device_id,'Account',account_id FROM account_devices
), walk(kind,id,depth) AS (
 SELECT 'Account'::text,%(account)s::integer,0
 UNION
 SELECT e.dk,e.di,w.depth+1 FROM walk w JOIN edges e ON e.sk=w.kind AND e.si=w.id
 WHERE w.depth < %(depth)s
)
SELECT c.region,COUNT(DISTINCT w.id)::bigint AS account_count
FROM walk w JOIN accounts a ON w.kind='Account' AND a.account_id=w.id
JOIN customers c ON c.customer_id=a.customer_id
WHERE w.depth>0 AND w.id<>%(account)s
GROUP BY c.region ORDER BY c.region""",
"Q5": """SELECT t1.transfer_id AS transfer_1,t2.transfer_id AS transfer_2,
 t3.transfer_id AS transfer_3,t3.receiver_id AS final_receiver
FROM transfers t1
JOIN transfers t2 ON t2.sender_id=t1.receiver_id AND t2.occurred_at>t1.occurred_at
 AND t2.occurred_at<=t1.occurred_at+600
JOIN transfers t3 ON t3.sender_id=t2.receiver_id AND t3.occurred_at>t2.occurred_at
 AND t3.occurred_at<=t2.occurred_at+600
WHERE t1.sender_id=%(account)s AND t1.occurred_at >= %(start)s AND t1.occurred_at < %(end)s
 AND t1.sender_id<>t1.receiver_id AND t1.sender_id<>t2.receiver_id
 AND t1.sender_id<>t3.receiver_id AND t1.receiver_id<>t2.receiver_id
 AND t1.receiver_id<>t3.receiver_id AND t2.receiver_id<>t3.receiver_id
 AND 90::bigint*t1.amount_rwf<=100::bigint*t2.amount_rwf
 AND 100::bigint*t2.amount_rwf<=105::bigint*t1.amount_rwf
 AND 90::bigint*t2.amount_rwf<=100::bigint*t3.amount_rwf
 AND 100::bigint*t3.amount_rwf<=105::bigint*t2.amount_rwf
ORDER BY 1,2,3,4""",
"Q6": """WITH RECURSIVE paths(current_id,ids,first_at,last_at,last_amount,n) AS (
 SELECT t.receiver_id,ARRAY[t.transfer_id]::bigint[],t.occurred_at,t.occurred_at,t.amount_rwf,1
 FROM transfers t WHERE t.sender_id=%(account)s AND t.occurred_at >= %(start)s AND t.occurred_at < %(end)s
 UNION ALL
 SELECT t.receiver_id,p.ids||t.transfer_id,p.first_at,t.occurred_at,t.amount_rwf,p.n+1
 FROM paths p JOIN transfers t ON t.sender_id=p.current_id
 WHERE p.current_id<>%(account)s AND p.n<8
   AND t.occurred_at >= %(start)s AND t.occurred_at < %(end)s
   AND t.occurred_at>p.last_at AND t.occurred_at-p.first_at<=1800
   AND 90::bigint*p.last_amount<=100::bigint*t.amount_rwf
   AND 100::bigint*t.amount_rwf<=105::bigint*p.last_amount
)
SELECT ids AS transfer_ids,n AS length FROM paths
WHERE current_id=%(account)s AND n BETWEEN 3 AND 8 ORDER BY ids""",
"Q7": """WITH RECURSIVE walk(account_id,depth,path) AS (
 SELECT %(account)s::integer,0,ARRAY[%(account)s::integer]
 UNION ALL
 SELECT t.receiver_id,w.depth+1,w.path||t.receiver_id
 FROM walk w JOIN transfers t ON t.sender_id=w.account_id
 JOIN accounts a ON a.account_id=t.receiver_id AND a.role='person'
 WHERE w.depth<%(depth)s AND NOT t.receiver_id=ANY(w.path)
   AND EXISTS (SELECT 1 FROM accounts s WHERE s.account_id=w.account_id AND s.role='person')
)
SELECT MIN(depth)::int AS min_length FROM walk WHERE account_id=%(destination)s AND depth>0""",
}

# Q7 improvement: deduplicate account/depth states rather than enumerate every
# path. This is the selected SQL version for comparison and final benchmarking.
SQL_Q7_BASELINE = SQL["Q7"]
SQL_Q7_IMPROVED = """WITH RECURSIVE walk(account_id,depth) AS (
 SELECT a.account_id,0 FROM accounts a
 WHERE a.account_id=%(account)s AND a.role='person'
 UNION
 SELECT t.receiver_id,w.depth+1
 FROM walk w JOIN transfers t ON t.sender_id=w.account_id
 JOIN accounts a ON a.account_id=t.receiver_id AND a.role='person'
 WHERE w.depth<%(depth)s
)
SELECT MIN(depth)::int AS min_length FROM walk
WHERE account_id=%(destination)s AND depth>0"""
SQL["Q7"] = SQL_Q7_IMPROVED

SQL_Q7_PATH = """WITH RECURSIVE walk(account_id,depth,accounts,transfer_ids) AS (
 SELECT a.account_id,0,ARRAY[a.account_id]::integer[],ARRAY[]::bigint[]
 FROM accounts a WHERE a.account_id=%(account)s AND a.role='person'
 UNION ALL
 SELECT t.receiver_id,w.depth+1,w.accounts||t.receiver_id,w.transfer_ids||t.transfer_id
 FROM walk w JOIN transfers t ON t.sender_id=w.account_id
 JOIN accounts a ON a.account_id=t.receiver_id AND a.role='person'
 WHERE w.depth<%(depth)s AND NOT t.receiver_id=ANY(w.accounts)
)
SELECT depth AS min_length,accounts,transfer_ids FROM walk
WHERE account_id=%(destination)s AND depth>0
ORDER BY depth,transfer_ids LIMIT 1"""

CYPHER_Q7_PATH = """MATCH (s:Account {account_id:$account,role:'person'}),(d:Account {account_id:$destination,role:'person'}) MATCH p=shortestPath((s)-[:TRANSFER*1..6]->(d)) WHERE all(n IN nodes(p) WHERE n.role='person') AND length(p)<=$depth RETURN length(p) AS min_length,[n IN nodes(p)|n.account_id] AS accounts,[r IN relationships(p)|r.transfer_id] AS transfer_ids"""

CYPHER = {
"Q1": """MATCH (a:Account {account_id:$account})-[t:TRANSFER]->() WHERE t.occurred_at >= $start AND t.occurred_at < $end RETURN count(t) AS transfer_count, coalesce(sum(t.amount_rwf),0) AS total_rwf""",
"Q2": """MATCH ()-[t:TRANSFER]->() WITH date(datetime({epochSeconds:t.occurred_at, timezone:'Africa/Kigali'})) AS cat_date,t RETURN cat_date,count(t) AS transfer_count,sum(t.amount_rwf) AS total_rwf ORDER BY cat_date""",
"Q3": """MATCH (a:Account {account_id:$account})-[u:USED_DEVICE]->(d:Device)<-[v:USED_DEVICE]-(b:Account) WHERE b.account_id<>$account AND u.first_day<=v.last_day AND v.first_day<=u.last_day RETURN DISTINCT b.account_id AS other_account,d.device_id AS device_id,d.access_type AS access_type,CASE WHEN u.first_day>v.first_day THEN u.first_day ELSE v.first_day END AS overlap_start,CASE WHEN u.last_day<v.last_day THEN u.last_day ELSE v.last_day END AS overlap_end ORDER BY other_account,device_id""",
"Q4": """MATCH (a:Account {account_id:$account}) MATCH p=(a)-[:OWNS|USED_DEVICE*1..10]-(b:Account) WHERE length(p)<=$depth AND b.account_id<>$account WITH DISTINCT b MATCH (c:Customer)-[:OWNS]->(b) RETURN c.region AS region,count(DISTINCT b) AS account_count ORDER BY region""",
"Q5": """MATCH (a:Account {account_id:$account})-[t1:TRANSFER]->(b:Account)-[t2:TRANSFER]->(c:Account)-[t3:TRANSFER]->(d:Account) WHERE t1.occurred_at >= $start AND t1.occurred_at < $end AND t2.occurred_at>t1.occurred_at AND t2.occurred_at<=t1.occurred_at+600 AND t3.occurred_at>t2.occurred_at AND t3.occurred_at<=t2.occurred_at+600 AND a<>b AND a<>c AND a<>d AND b<>c AND b<>d AND c<>d AND 90*t1.amount_rwf<=100*t2.amount_rwf AND 100*t2.amount_rwf<=105*t1.amount_rwf AND 90*t2.amount_rwf<=100*t3.amount_rwf AND 100*t3.amount_rwf<=105*t2.amount_rwf RETURN t1.transfer_id AS transfer_1,t2.transfer_id AS transfer_2,t3.transfer_id AS transfer_3,d.account_id AS final_receiver ORDER BY transfer_1,transfer_2,transfer_3,final_receiver""",
"Q6": "",
"Q7": """MATCH (s:Account {account_id:$account,role:'person'}),(d:Account {account_id:$destination,role:'person'}) MATCH p=shortestPath((s)-[:TRANSFER*1..6]->(d)) WHERE all(n IN nodes(p) WHERE n.role='person') AND length(p)<=$depth RETURN length(p) AS min_length""",
}


def _q6_branch(length):
    nodes = [f"n{i}" for i in range(1, length)]
    lines = ["MATCH (a:Account {account_id:$account})-[t0:TRANSFER]->(n1)",
             "WHERE t0.occurred_at >= $start AND t0.occurred_at < $end AND n1<>a"]
    for i in range(1, length):
        target = "a" if i == length - 1 else f"n{i+1}"
        lines.append(f"MATCH (n{i})-[t{i}:TRANSFER]->({target})")
        checks = [f"t{i}.occurred_at >= $start", f"t{i}.occurred_at < $end",
                  f"t{i}.occurred_at > t{i-1}.occurred_at",
                  f"t{i}.occurred_at - t0.occurred_at <= 1800",
                  f"90*t{i-1}.amount_rwf <= 100*t{i}.amount_rwf",
                  f"100*t{i}.amount_rwf <= 105*t{i-1}.amount_rwf"]
        if i < length - 1:
            checks.append(f"n{i+1}<>a")
        lines.append("WHERE " + " AND ".join(checks))
    ids = ",".join(f"t{i}.transfer_id" for i in range(length))
    lines.append(f"RETURN [{ids}] AS transfer_ids,{length} AS length")
    return "\n".join(lines)


CYPHER["Q6"] = "\nUNION ALL\n".join(_q6_branch(n) for n in range(3, 9)) + "\nORDER BY transfer_ids"
