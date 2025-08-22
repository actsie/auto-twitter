-- Create discovery_lists table for dynamic Twitter lists management
CREATE TABLE IF NOT EXISTS discovery_lists (
    id SERIAL PRIMARY KEY,
    list_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    member_count INTEGER,
    is_private BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_used TIMESTAMP WITH TIME ZONE
);

-- Create index on list_id for faster lookups
CREATE INDEX IF NOT EXISTS idx_discovery_lists_list_id ON discovery_lists(list_id);

-- Create index on is_active for faster filtering
CREATE INDEX IF NOT EXISTS idx_discovery_lists_is_active ON discovery_lists(is_active);

-- Enable Row Level Security if needed
-- ALTER TABLE discovery_lists ENABLE ROW LEVEL SECURITY;

-- Create a trigger to update updated_at automatically
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_discovery_lists_updated_at
    BEFORE UPDATE ON discovery_lists
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Insert the existing hardcoded lists as initial data
INSERT INTO discovery_lists (list_id, name, description, is_active)
VALUES 
    ('1957324919269929248', 'Main AI/Tech List', 'Primary AI and technology focused Twitter list', true),
    ('1278784207641284609', 'Secondary AI List', 'Secondary AI and ML focused Twitter list', true)
ON CONFLICT (list_id) DO NOTHING;