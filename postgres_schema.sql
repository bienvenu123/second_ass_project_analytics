-- PostgreSQL 16+; run in the project database.
SET TIME ZONE 'Africa/Kigali';

CREATE TABLE customers (
  customer_id INTEGER PRIMARY KEY,
  region TEXT NOT NULL
);
CREATE TABLE accounts (
  account_id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
  role TEXT NOT NULL CHECK (role IN ('person', 'merchant', 'agent'))
);
CREATE TABLE devices (
  device_id INTEGER PRIMARY KEY,
  access_type TEXT NOT NULL
);
CREATE TABLE account_devices (
  account_id INTEGER NOT NULL REFERENCES accounts(account_id),
  device_id INTEGER NOT NULL REFERENCES devices(device_id),
  first_day SMALLINT NOT NULL,
  last_day SMALLINT NOT NULL,
  observations INTEGER NOT NULL CHECK (observations > 0),
  PRIMARY KEY (account_id, device_id),
  CHECK (0 <= first_day AND first_day <= last_day AND last_day <= 29)
);
CREATE TABLE transfers (
  transfer_id BIGINT PRIMARY KEY,
  sender_id INTEGER NOT NULL REFERENCES accounts(account_id),
  receiver_id INTEGER NOT NULL REFERENCES accounts(account_id),
  occurred_at BIGINT NOT NULL,
  amount_rwf INTEGER NOT NULL CHECK (amount_rwf > 0)
);

-- Load the CSVs first, then run postgres_indexes.sql and ANALYZE.
