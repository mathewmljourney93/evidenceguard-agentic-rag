-- Runs once, when the Compose volume is first initialised.
-- Creates the disposable database used by the integration tests (EG_TEST_DATABASE_URL).
-- Integration tests refuse any database whose name does not end in "_test".
CREATE DATABASE evidenceguard_test;
