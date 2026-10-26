CREATE ROLE order_app LOGIN PASSWORD 'order_app_lab_pass';
GRANT CONNECT ON DATABASE eventstore_db TO order_app;
GRANT USAGE ON SCHEMA public TO order_app;