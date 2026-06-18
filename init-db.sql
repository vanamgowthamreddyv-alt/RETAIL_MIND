-- ==========================================
-- RAG_APP Database Initialization
-- PostgreSQL Setup for Data_Analytics
-- ==========================================

-- Connect to the database created by Docker
\c Data_Analytics;

-- ==========================================
-- Extensions
-- ==========================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ==========================================
-- Users Table
-- ==========================================
CREATE TABLE IF NOT EXISTS user_details (
    id SERIAL PRIMARY KEY,
    user_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_email ON user_details(email);

-- ==========================================
-- Sales Table
-- ==========================================
CREATE TABLE IF NOT EXISTS sales (
    id SERIAL PRIMARY KEY,
    shopkeeper_id INTEGER NOT NULL REFERENCES user_details(id) ON DELETE CASCADE,
    product_name VARCHAR(100) NOT NULL,
    price NUMERIC(10, 2) NOT NULL CHECK (price > 0),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    total NUMERIC(10, 2) NOT NULL CHECK (total > 0),
    sale_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_total CHECK (total = price * quantity)
);

CREATE INDEX IF NOT EXISTS idx_sales_shopkeeper_id ON sales(shopkeeper_id);
CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(sale_date);
CREATE INDEX IF NOT EXISTS idx_sales_product ON sales(product_name);

-- ==========================================
-- Documents Table (RAG)
-- ==========================================
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    doc_id VARCHAR(255) UNIQUE NOT NULL,
    shopkeeper_id INTEGER REFERENCES user_details(id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    file_path VARCHAR(500),
    file_size INTEGER,
    file_hash VARCHAR(64) UNIQUE,
    content_preview TEXT,
    page_count INTEGER,
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_doc_shopkeeper_id ON documents(shopkeeper_id);
CREATE INDEX IF NOT EXISTS idx_doc_status ON documents(status);

-- ==========================================
-- Audit Logs
-- ==========================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES user_details(id) ON DELETE CASCADE,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id INTEGER,
    old_values JSONB,
    new_values JSONB,
    ip_address VARCHAR(45),
    user_agent TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_user_id ON audit_logs(user_id);

-- ==========================================
-- Default Admin User
-- ==========================================
INSERT INTO user_details (user_name, email, password)
VALUES (
    'Admin User',
    'admin@rag-app.local',
    '$2b$12$R9h7cIPz0gi.URNNX3kh2OPST9/PgBkqquzi.Ss7KIUgO2t0jKMm'
)
ON CONFLICT (email) DO NOTHING;