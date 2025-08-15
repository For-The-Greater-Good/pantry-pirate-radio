-- Add timestamp columns to tables that are missing them
-- These are defined in SQLAlchemy models but missing from database

-- Add timestamps to location table
ALTER TABLE location 
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- Add timestamps to organization table
ALTER TABLE organization
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- Add timestamps to service table  
ALTER TABLE service
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- Add timestamps to physical_address table
ALTER TABLE physical_address
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- Add timestamps to phone table
ALTER TABLE phone
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_location_created_at ON location(created_at);
CREATE INDEX IF NOT EXISTS idx_location_updated_at ON location(updated_at);
CREATE INDEX IF NOT EXISTS idx_organization_created_at ON organization(created_at);
CREATE INDEX IF NOT EXISTS idx_organization_updated_at ON organization(updated_at);
CREATE INDEX IF NOT EXISTS idx_service_created_at ON service(created_at);
CREATE INDEX IF NOT EXISTS idx_service_updated_at ON service(updated_at);

-- Add comments
COMMENT ON COLUMN location.created_at IS 'Timestamp when record was created';
COMMENT ON COLUMN location.updated_at IS 'Timestamp when record was last updated';
COMMENT ON COLUMN organization.created_at IS 'Timestamp when record was created';
COMMENT ON COLUMN organization.updated_at IS 'Timestamp when record was last updated';
COMMENT ON COLUMN service.created_at IS 'Timestamp when record was created';
COMMENT ON COLUMN service.updated_at IS 'Timestamp when record was last updated';

-- Create trigger function to auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for auto-updating updated_at
CREATE TRIGGER update_location_updated_at BEFORE UPDATE ON location
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_organization_updated_at BEFORE UPDATE ON organization
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_service_updated_at BEFORE UPDATE ON service
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_physical_address_updated_at BEFORE UPDATE ON physical_address
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_phone_updated_at BEFORE UPDATE ON phone
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();