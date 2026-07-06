-- Multi-asset support. Introduces the asset-class discriminator so bonds and listed
-- equities share one security master, one order model and one position model rather than
-- living in parallel silos. Equities carry a ticker and have no coupon/maturity/rating,
-- so those bond-only columns are relaxed to nullable.

ALTER TABLE security ADD COLUMN asset_class VARCHAR(16) NOT NULL DEFAULT 'FIXED_INCOME';
ALTER TABLE security ADD COLUMN ticker      VARCHAR(12);

ALTER TABLE security ALTER COLUMN coupon_rate   DROP NOT NULL;
ALTER TABLE security ALTER COLUMN maturity_date DROP NOT NULL;
ALTER TABLE security ALTER COLUMN face_value    DROP NOT NULL;
ALTER TABLE security ALTER COLUMN rating        DROP NOT NULL;

CREATE INDEX idx_security_asset_class ON security (asset_class);
