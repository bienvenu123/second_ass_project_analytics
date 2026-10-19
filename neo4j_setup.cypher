CREATE CONSTRAINT customer_id IF NOT EXISTS FOR (n:Customer) REQUIRE n.customer_id IS UNIQUE;
CREATE CONSTRAINT account_id IF NOT EXISTS FOR (n:Account) REQUIRE n.account_id IS UNIQUE;
CREATE CONSTRAINT device_id IF NOT EXISTS FOR (n:Device) REQUIRE n.device_id IS UNIQUE;
CREATE INDEX transfer_occurred_at IF NOT EXISTS FOR ()-[r:TRANSFER]-() ON (r.occurred_at);

// Wait for all indexes to become ONLINE in :schema before verification.
MATCH (n:Customer) RETURN count(n) AS customers;
MATCH (n:Account) RETURN count(n) AS accounts;
MATCH (n:Device) RETURN count(n) AS devices;
MATCH ()-[r:OWNS]->() RETURN count(r) AS owns;
MATCH ()-[r:USED_DEVICE]->() RETURN count(r) AS used_device;
MATCH ()-[r:TRANSFER]->() RETURN count(r) AS transfers,
       min(r.occurred_at) AS earliest, max(r.occurred_at) AS latest,
       sum(r.amount_rwf) AS sum_amount_rwf, count(DISTINCT r.transfer_id) AS unique_transfer_ids;
MATCH (c:Customer)-[r:OWNS]->(a:Account)
WITH a,count(DISTINCT c) AS owners
WHERE owners<>1
RETURN count(a) AS accounts_with_wrong_owner_count;
MATCH (a:Account) RETURN a.role AS role,count(*) AS accounts ORDER BY role;
