-- Beispiel-Stammdaten fuer die Beauftragungsplanung.
-- Auf eine LEERE oder Test-DB anwenden und Werte anpassen.

INSERT INTO plan_ea_metadata (year, ea_number, gewerk, project_group, is_active, note)
VALUES
  (2026, '0043402', 'SYS', 'CSP', 1, 'EA Beispiel 1'),
  (2026, '0043403', 'SYS', 'CSP', 1, 'EA Beispiel 2'),
  (2026, '0043404', 'SYS', NULL, 1, 'EA Beispiel 3');

INSERT INTO plan_company_targets (year, company, gewerk, quarter, target_value, annual_target, quarter_cap, step_value)
VALUES
  (2026, 'EDAG', 'SYS', 'Q1', 100000, 400000, 100000, 25000),
  (2026, 'EDAG', 'SYS', 'Q2', 100000, 400000, 100000, 25000),
  (2026, 'EDAG', 'SYS', 'Q3', 100000, 400000, 100000, 25000),
  (2026, 'EDAG', 'SYS', 'Q4', 100000, 400000, 100000, 25000),
  (2026, 'BERTRANDT', 'SYS', 'Q1', 50000, 200000, 50000, 10000),
  (2026, 'BERTRANDT', 'SYS', 'Q2', 50000, 200000, 50000, 10000),
  (2026, 'BERTRANDT', 'SYS', 'Q3', 50000, 200000, 50000, 10000),
  (2026, 'BERTRANDT', 'SYS', 'Q4', 50000, 200000, 50000, 10000);

INSERT INTO plan_existing_orders (year, company, gewerk, quarter, ea_number, amount, is_fixed, can_stop, note)
VALUES
  (2026, 'EDAG', 'SYS', 'Q1', '0043402', 50000, 1, 0, 'Fixierter Bestand'),
  (2026, 'BERTRANDT', 'SYS', 'Q1', '0043403', 20000, 0, 1, 'Im Durchlauf');

INSERT INTO plan_reference_orders (year, ea_number, reference_value, reference_count, source_company, gewerk, note)
VALUES
  (2026, '0043402', 180000, 4, 'EDAG', 'SYS', 'btl_ref'),
  (2026, '0043403', 120000, 3, 'EDAG', 'SYS', 'btl_ref'),
  (2026, '0043402', 90000, 2, 'BERTRANDT', 'SYS', 'btl_ref');

INSERT INTO plan_group_rules (year, group_code, target_value, is_hard, note)
VALUES
  (2026, 'CSP', 250000, 1, 'CSP Gruppensumme hart');

INSERT INTO plan_group_members (year, group_code, ea_number, fixed_target_value, min_value, max_value, is_hard, note)
VALUES
  (2026, 'CSP', '0043402', NULL, 50000, NULL, 0, 'Min. sinnvoller Anteil'),
  (2026, 'CSP', '0043403', NULL, 50000, NULL, 0, 'Min. sinnvoller Anteil');
