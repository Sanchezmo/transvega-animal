"""
Inicialización de base de datos auditoría - SQL para PostgreSQL.
"""
-- Extensiones necesarias
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Tabla principal de auditoría
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Identificación de la petición
    request_id UUID NOT NULL,
    correlation_id UUID,
    
    -- Agente/Usuario
    agent_id VARCHAR(100),
    agent_name VARCHAR(100),
    agent_roles JSONB,
    api_key_hash VARCHAR(64),
    
    -- Petición HTTP
    method VARCHAR(10) NOT NULL,
    path VARCHAR(500) NOT NULL,
    query_params JSONB,
    request_body_hash VARCHAR(64),
    
    -- Respuesta
    status_code INT,
    response_body_hash VARCHAR(64),
    duration_ms NUMERIC(10,2),
    
    -- Recurso afectado
    resource_type VARCHAR(100),
    resource_id VARCHAR(100),
    action VARCHAR(50) NOT NULL,
    
    -- Estado antes/después
    previous_state JSONB,
    new_state JSONB,
    diff JSONB,
    
    -- Idempotencia
    idempotency_key VARCHAR(100),
    idempotent BOOLEAN DEFAULT FALSE,
    
    -- Metadatos
    user_agent TEXT,
    client_ip INET,
    metadata JSONB,
    
    -- Resultado
    success BOOLEAN NOT NULL DEFAULT TRUE,
    error_code VARCHAR(50),
    error_message TEXT,
    error_details JSONB,
    
    -- Trazabilidad
    trace_id UUID,
    span_id UUID,
    parent_span_id UUID
);

-- Índices para consultas frecuentes
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_agent ON audit_log(agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_resource ON audit_log(resource_type, resource_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_request_id ON audit_log(request_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_idempotency ON audit_log(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_audit_log_correlation ON audit_log(correlation_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_success ON audit_log(success, created_at DESC);

-- Tabla de solicitudes de aprobación
CREATE TABLE IF NOT EXISTS approval_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Solicitante
    agent_id VARCHAR(100) NOT NULL,
    agent_name VARCHAR(100) NOT NULL,
    
    -- Acción solicitada
    action VARCHAR(100) NOT NULL,
    action_type VARCHAR(50) NOT NULL, -- publish, price_change, discount, invoice_validate, payment, etc.
    reason TEXT NOT NULL,
    
    -- Datos afectados
    resource_type VARCHAR(100) NOT NULL,
    resource_id VARCHAR(100) NOT NULL,
    current_state JSONB,
    proposed_state JSONB NOT NULL,
    
    -- Evaluación de riesgo
    risk_level VARCHAR(20) NOT NULL DEFAULT 'medium', -- low, medium, high, critical
    risk_factors JSONB,
    
    -- Evidencias
    evidence_urls JSONB,
    evidence_notes TEXT,
    
    -- Flujo de aprobación
    status VARCHAR(30) NOT NULL DEFAULT 'pending', -- pending, approved, rejected, expired, cancelled
    priority INTEGER DEFAULT 0,
    
    -- Aprobador
    approved_by VARCHAR(100),
    approved_at TIMESTAMPTZ,
    approval_comment TEXT,
    rejection_reason TEXT,
    
    -- Expiración
    expires_at TIMESTAMPTZ,
    auto_approve_at TIMESTAMPTZ,
    auto_reject_at TIMESTAMPTZ,
    
    -- Notificaciones
    notification_sent BOOLEAN DEFAULT FALSE,
    notification_channels JSONB,
    
    -- Metadatos
    request_id UUID,
    correlation_id UUID,
    metadata JSONB,
    
    -- Idempotencia
    idempotency_key VARCHAR(100) UNIQUE,
    
    -- Auditoría
    audit_log_id UUID REFERENCES audit_log(id)
);

CREATE INDEX IF NOT EXISTS idx_approval_requests_status ON approval_requests(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_approval_requests_agent ON approval_requests(agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_approval_requests_resource ON approval_requests(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_approval_requests_expires ON approval_requests(expires_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_approval_requests_idempotency ON approval_requests(idempotency_key);

-- Tabla de cola de tareas
CREATE TABLE IF NOT EXISTS task_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    
    -- Identificación
    task_id VARCHAR(100) NOT NULL UNIQUE,
    task_type VARCHAR(100) NOT NULL,
    task_name VARCHAR(200),
    
    -- Prioridad y estado
    priority INTEGER DEFAULT 0, -- -10 a 10
    status VARCHAR(30) NOT NULL DEFAULT 'pending', -- pending, queued, running, waiting_approval, completed, failed, cancelled
    
    -- Agente responsable
    agent_id VARCHAR(100),
    agent_name VARCHAR(100),
    
    -- Datos de entrada/salida
    input_data JSONB NOT NULL,
    output_data JSONB,
    error_data JSONB,
    
    -- Reintentos
    attempt INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    last_error TEXT,
    retry_at TIMESTAMPTZ,
    
    -- Programación
    scheduled_at TIMESTAMPTZ,
    timeout_seconds INTEGER DEFAULT 3600,
    
    -- Aprobación
    requires_approval BOOLEAN DEFAULT FALSE,
    approval_id UUID REFERENCES approval_requests(id),
    
    -- Idempotencia
    idempotency_key VARCHAR(100) UNIQUE,
    
    -- Referencias
    resource_type VARCHAR(100),
    resource_id VARCHAR(100),
    reference_id UUID,
    correlation_id UUID,
    
    -- Progreso
    progress_percent INTEGER DEFAULT 0,
    progress_message TEXT,
    
    -- Metadatos
    tags JSONB,
    metadata JSONB,
    
    -- Trazabilidad
    parent_task_id UUID REFERENCES task_queue(id),
    root_task_id UUID REFERENCES task_queue(id),
    
    -- Auditoría
    created_by VARCHAR(100),
    assigned_to VARCHAR(100),
    completed_by VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_task_queue_status ON task_queue(status, priority DESC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_task_queue_agent ON task_queue(agent_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_queue_scheduled ON task_queue(scheduled_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_task_queue_idempotency ON task_queue(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_task_queue_correlation ON task_queue(correlation_id);
CREATE INDEX IF NOT EXISTS idx_task_queue_resource ON task_queue(resource_type, resource_id);

-- Tabla de sesiones de agente (para JWT refresh tokens)
CREATE TABLE IF NOT EXISTS agent_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    
    agent_id VARCHAR(100) NOT NULL,
    agent_name VARCHAR(100) NOT NULL,
    roles JSONB,
    
    access_token_hash VARCHAR(64) NOT NULL,
    refresh_token_hash VARCHAR(64) NOT NULL UNIQUE,
    
    ip_address INET,
    user_agent TEXT,
    
    revoked BOOLEAN DEFAULT FALSE,
    revoked_at TIMESTAMPTZ,
    revoked_reason TEXT,
    
    last_activity TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_sessions_agent ON agent_sessions(agent_id, expires_at);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_refresh ON agent_sessions(refresh_token_hash);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_expires ON agent_sessions(expires_at) WHERE revoked = FALSE;

-- Función para actualizar updated_at automáticamente
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers para updated_at
DROP TRIGGER IF EXISTS update_approval_requests_updated_at ON approval_requests;
CREATE TRIGGER update_approval_requests_updated_at
    BEFORE UPDATE ON approval_requests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_task_queue_updated_at ON task_queue;
CREATE TRIGGER update_task_queue_updated_at
    BEFORE UPDATE ON task_queue
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_agent_sessions_updated_at ON agent_sessions;
CREATE TRIGGER update_agent_sessions_updated_at
    BEFORE UPDATE ON agent_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Vista para auditoría rápida
CREATE OR REPLACE VIEW audit_summary AS
SELECT 
    DATE_TRUNC('day', created_at) as day,
    agent_name,
    action,
    resource_type,
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE success) as successful,
    COUNT(*) FILTER (WHERE NOT success) as failed,
    AVG(duration_ms) as avg_duration_ms
FROM audit_log
GROUP BY DATE_TRUNC('day', created_at), agent_name, action, resource_type
ORDER BY day DESC, total DESC;

-- Función para limpiar logs antiguos (retención configurable)
CREATE OR REPLACE FUNCTION cleanup_old_audit_logs(retention_days INTEGER DEFAULT 90)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM audit_log
    WHERE created_at < NOW() - INTERVAL '1 day' * retention_days
    AND success = TRUE
    AND action NOT IN ('login', 'logout', 'permission_change');
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Comentarios en tablas
COMMENT ON TABLE audit_log IS 'Registro inmutable de auditoría de todas las operaciones del sistema';
COMMENT ON TABLE approval_requests IS 'Solicitudes de aprobación humana para acciones sensibles';
COMMENT ON TABLE task_queue IS 'Cola de tareas asíncronas para procesamiento en background';
COMMENT ON TABLE agent_sessions IS 'Sesiones de agentes para gestión de tokens JWT';