CREATE INDEX accounts_customer_account_idx ON accounts(customer_id, account_id);
CREATE INDEX account_devices_device_account_idx ON account_devices(device_id, account_id);
CREATE INDEX transfers_sender_time_idx ON transfers(sender_id, occurred_at)
  INCLUDE (receiver_id, amount_rwf, transfer_id);
CREATE INDEX transfers_receiver_time_idx ON transfers(receiver_id, occurred_at)
  INCLUDE (sender_id, amount_rwf, transfer_id);
CREATE INDEX transfers_occurred_brin_idx ON transfers USING BRIN(occurred_at);
ANALYZE;
